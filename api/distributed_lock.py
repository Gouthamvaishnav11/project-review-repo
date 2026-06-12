"""
Distributed Lock Utility for Payment Processing
Uses Redis to ensure sequential processing of payments per folio.

Author: Krish Vishwakarma
Date: 29th Jan 2026
Purpose: Prevent race conditions in concurrent payment processing
"""

import frappe
import redis
import time
from contextlib import contextmanager
from typing import Optional


class DistributedLock:
	"""
	Redis-based distributed lock for ensuring sequential payment processing.
	
	Usage:
		with DistributedLock("payment:FOL-123", timeout=30) as lock:
			if lock.acquired:
				# Process payment
				pass
			else:
				# Lock acquisition failed
				raise Exception("Could not acquire lock")
	"""
	
	def __init__(self, lock_key: str, timeout: int = 30, blocking_timeout: int = 25):
		"""
		Initialize distributed lock.
		
		Args:
			lock_key: Unique key for the lock (e.g., "payment:FOL-123")
			timeout: How long to hold the lock before auto-release (seconds)
			blocking_timeout: How long to wait to acquire lock (seconds)
		"""
		self.lock_key = f"ecohotels:lock:{lock_key}"
		self.timeout = timeout
		self.blocking_timeout = blocking_timeout
		self.redis_client = None
		self.lock = None
		self.acquired = False
		
	def _get_redis_client(self) -> redis.Redis:
		"""Get Redis client from Frappe's cache or create new connection."""
		try:
			# Try to use Frappe's Redis connection
			from frappe.utils.redis_wrapper import RedisWrapper
			redis_client = frappe.cache()
			
			# Frappe's cache is a wrapper, get the underlying Redis client
			if hasattr(redis_client, 'redis_client'):
				return redis_client.redis_client
			elif hasattr(redis_client, '_redis'):
				return redis_client._redis
			else:
				# Fallback: create direct connection
				return self._create_redis_connection()
				
		except Exception as e:
			frappe.log_error(
				title="Distributed Lock: Redis Connection Error",
				message=f"Error getting Redis client: {str(e)}\nFalling back to direct connection."
			)
			return self._create_redis_connection()
	
	def _create_redis_connection(self) -> redis.Redis:
		"""Create direct Redis connection using Frappe's config."""
		try:
			# Get Redis config from Frappe
			redis_config = frappe.conf.get('redis_cache') or frappe.conf.get('redis_queue')
			
			if isinstance(redis_config, str):
				# Parse redis://host:port format
				return redis.from_url(redis_config)
			elif isinstance(redis_config, dict):
				# Use dict config
				return redis.Redis(
					host=redis_config.get('host', 'localhost'),
					port=redis_config.get('port', 6379),
					db=redis_config.get('db', 0),
					password=redis_config.get('password'),
					decode_responses=True
				)
			else:
				# Default localhost connection
				return redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
				
		except Exception as e:
			frappe.log_error(
				title="Distributed Lock: Redis Connection Failed",
				message=f"Could not create Redis connection: {str(e)}"
			)
			raise
	
	def acquire(self) -> bool:
		"""
		Acquire the distributed lock.
		
		Returns:
			bool: True if lock was acquired, False otherwise
		"""
		try:
			self.redis_client = self._get_redis_client()
			
			# Create Redis lock
			self.lock = self.redis_client.lock(
				self.lock_key,
				timeout=self.timeout,
				blocking_timeout=self.blocking_timeout
			)
			
			# Try to acquire
			self.acquired = self.lock.acquire(blocking=True)
			
			if self.acquired:
				frappe.log_error(
					title=f"Distributed Lock: Acquired",
					message=f"Lock acquired for key: {self.lock_key}"
				)
			else:
				frappe.log_error(
					title=f"Distributed Lock: Failed to Acquire",
					message=f"Could not acquire lock for key: {self.lock_key} after {self.blocking_timeout}s"
				)
			
			return self.acquired
			
		except redis.exceptions.LockError as e:
			frappe.log_error(
				title="Distributed Lock: Lock Error",
				message=f"Redis lock error for key {self.lock_key}: {str(e)}"
			)
			self.acquired = False
			return False
			
		except Exception as e:
			frappe.log_error(
				title="Distributed Lock: Unexpected Error",
				message=f"Unexpected error acquiring lock for key {self.lock_key}: {str(e)}\n{frappe.get_traceback()}"
			)
			self.acquired = False
			return False
	
	def release(self):
		"""Release the distributed lock."""
		if self.lock and self.acquired:
			try:
				self.lock.release()
				frappe.log_error(
					title=f"Distributed Lock: Released",
					message=f"Lock released for key: {self.lock_key}"
				)
			except redis.exceptions.LockError as e:
				# Lock may have already expired or been released
				frappe.log_error(
					title="Distributed Lock: Release Error",
					message=f"Error releasing lock for key {self.lock_key}: {str(e)}"
				)
			except Exception as e:
				frappe.log_error(
					title="Distributed Lock: Unexpected Release Error",
					message=f"Unexpected error releasing lock for key {self.lock_key}: {str(e)}"
				)
			finally:
				self.acquired = False
	
	def __enter__(self):
		"""Context manager entry."""
		self.acquire()
		return self
	
	def __exit__(self, exc_type, exc_val, exc_tb):
		"""Context manager exit."""
		self.release()
		return False  # Don't suppress exceptions


@contextmanager
def payment_lock(folio_no: str, timeout: int = 30, blocking_timeout: int = 25):
	"""
	Context manager for payment processing locks.
	
	Usage:
		with payment_lock("FOL-123") as acquired:
			if not acquired:
				raise Exception("Another payment is being processed")
			# Process payment safely
	
	Args:
		folio_no: The folio number to lock
		timeout: Lock timeout in seconds (default: 30)
		blocking_timeout: How long to wait for lock (default: 25)
	
	Yields:
		bool: True if lock was acquired, False otherwise
	"""
	lock_key = f"payment:{folio_no}"
	lock = DistributedLock(lock_key, timeout=timeout, blocking_timeout=blocking_timeout)
	
	try:
		acquired = lock.acquire()
		yield acquired
	finally:
		lock.release()
