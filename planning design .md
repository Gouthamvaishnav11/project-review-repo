# Production Scheduler Module

## Overview

The Production Scheduler is an interactive manufacturing planning and execution dashboard designed for ERPNext/Frappe. It provides a visual timeline for scheduling Work Orders, Job Cards, Workstations, Breaks, Maintenance Activities, and Production Events.

The scheduler helps production managers plan, monitor, and optimize manufacturing operations through a drag-and-drop interface.

---

# Manufacturing Workflow

The scheduler follows the manufacturing process flow:

```text
Production Plan
    ↓
Production Plan Item
    ↓
Work Order
    ↓
Job Card
    ↓
Workstation
    ↓
Stock Entry
    ↓
Batch
    ↓
Finished Goods Warehouse
```

Example:

```text
Production Plan:
MFG-PP-2026-00026

Item:
FzG04313

Work Order:
MFG-WO-2026-00022

Job Cards:
PO-JOB00006 - AMF Mix Dough
PO-JOB00007 - AMF Mix Dough
PO-JOB00008 - AMF Proof Bread
PO-JOB00009 - AMF Bake Bread
PO-JOB00010 - AMF Freeze Bread
PO-JOB00011 - AMF Pack Bread
```

---

# Scheduler Views

The scheduler supports:

* Day View
* Week View
* Month View

Users can switch between views for detailed planning or long-term scheduling.

---

# Workstation-Based Planning

Production is scheduled against actual workstations.

Example:

Automated Frozen Line (AMF)

* Baker Perkins Inline Mixer
* Continuous Proofer
* AMF Tunnel Oven
* Blast Freezer
* Auto Wrapper (Palletizer)

Bread Production

* Dough Mixer

Workstations are displayed as scheduler rows.

---

# Job Card Scheduling

Each Job Card appears as a timeline block.

Displayed Information:

* Job Card Number
* Work Order
* Operation
* Item
* Quantity
* Workstation
* Planned Start Time
* Planned End Time
* Actual Start Time
* Actual End Time
* Status

Example:

```text
PO-JOB00009

Operation:
AMF Bake Bread

Workstation:
AMF Tunnel Oven

Planned:
02:20 AM - 02:50 AM

Actual:
19:34 - 19:34

Status:
Completed
```

---

# Drag and Drop Scheduling

The scheduler supports full drag-and-drop functionality.

## Job Card Drag & Drop

Production planners can:

* Move Job Cards to another time slot
* Move Job Cards to another workstation
* Reschedule production activities
* Adjust production sequences
* Resolve scheduling conflicts

Example:

```text
PO-JOB00009

Old Schedule:
02:20 AM - 02:50 AM

New Schedule:
03:00 AM - 03:30 AM
```

The scheduler automatically updates:

* Expected Start Date
* Expected End Date
* Resource Allocation
* Capacity Calculations

---

# Break Management

Breaks are managed as scheduler events.

Supported Break Types:

* Lunch Break
* Tea Break
* Cleaning
* Sanitation
* Maintenance
* Quality Inspection
* Emergency Stop
* Power Failure
* Team Meeting

---

# Drag and Drop Break Management

Breaks are fully draggable and resizable.

Users can:

* Create Break Events
* Move Breaks on Timeline
* Resize Break Duration
* Copy Breaks
* Apply Breaks to Multiple Workstations
* Schedule Recurring Breaks

Example:

```text
Lunch Break

12:30 PM - 01:00 PM

Drag:
01:00 PM - 01:30 PM
```

---

# Smart Conflict Detection

When a break or maintenance activity overlaps production:

The scheduler automatically detects conflicts.

Example:

```text
Workstation Occupied

AMF Tunnel Oven

Scheduled Job:
02:20 PM - 02:50 PM

Cleaning:
02:30 PM - 03:00 PM
```

Available Actions:

* Move Break
* Move Job Card
* Override Conflict
* Split Schedule

---

# Production Status Tracking

Status Indicators:

* Planned
* In Progress
* Completed
* Delayed
* On Hold
* Closed
* Cancelled

Color Coding:

* Blue → Planned
* Green → Completed
* Orange → In Progress
* Red → Delayed
* Purple → Break
* Yellow → Cleaning
* Gray → Maintenance

---

# Advanced Filters

Users can filter by:

* Production Plan
* Work Order
* Product
* Item Code
* Workstation
* Workstation Type
* Employee
* Status
* Date Range

---

# Planned vs Actual Analysis

The scheduler compares planned execution against actual execution.

Fields Used:

* expected_start_date
* expected_end_date
* actual_start_date
* actual_end_date

Benefits:

* Delay Analysis
* Efficiency Tracking
* Production Monitoring

---

# Workstation Utilization

The scheduler calculates workstation utilization.

Formula:

Utilization % =
Scheduled Time ÷ Available Time × 100

Benefits:

* Identify bottlenecks
* Detect idle resources
* Improve production planning

---

# KPI Dashboard

Dashboard Metrics:

* Total Production Plans
* Total Work Orders
* Running Jobs
* Completed Jobs
* Delayed Jobs
* Utilization Percentage
* Downtime Hours
* Production Quantity

---

# Future Enhancements

## AI-Based Scheduling

Automatically suggest:

* Best Workstation
* Best Production Sequence
* Capacity Balancing
* Shift Optimization

## Predictive Maintenance

Predict equipment failures using historical production data.

## Real-Time Monitoring

Live updates from:

* Job Cards
* Machines
* Operators
* Production Lines

---

# Expected Benefits

* Improved Production Visibility
* Better Resource Utilization
* Reduced Downtime
* Faster Scheduling
* Real-Time Tracking
* Better Production Planning
* Increased Manufacturing Efficiency

-


![alt text](image.png)

Start
  │
  ▼
Select Production Plan
  │
  ▼
Load Work Orders
  │
  ▼
Generate Job Cards
  │
  ▼
Assign Workstations
  │
  ▼
Display Scheduler
(Day / Week / Month)
  │
  ▼
Drag & Drop Job Cards
  │
  ▼
Check Resource Availability
  │
  ├── Conflict Found?
  │       │
  │       ├── Yes ──► Show Conflict
  │       │             │
  │       │             ▼
  │       │      Reschedule Job
  │       │
  │       └── No
  │
  ▼
Save Schedule
  │
  ▼
Add Break / Maintenance Events
  │
  ▼
Track Actual Start & End Times
  │
  ▼
Calculate Utilization & KPIs
  │
  ▼
Display Dashboard
  │
  ▼
End