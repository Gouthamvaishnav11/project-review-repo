frappe.ui.form.on('Sales Order', {
    refresh: function(frm) {
        if (!frm.is_new()) {
            ecohotels_render_soft_links(frm, 'Sales Invoice');
        }
    }
});

window.ecohotels_render_soft_links = function(frm, link_doctype) {
    frappe.call({
        method: 'ecohotels.api.soft_links.get_soft_linked_docs',
        args: {
            doctype: frm.doc.doctype,
            docname: frm.doc.name
        },
        callback: function(r) {
            if (r.message && r.message.length > 0) {
                let dashboard = frm.dashboard;
                let section_label = "Booking Links (Soft)";
                
                // Find or create custom section
                let $section = dashboard.wrapper.find(`.section-head:contains("${section_label}")`).parent();
                if ($section.length === 0) {
                   $section = $(`<div class="section-links" style="margin-top: 15px; border-top: 1px solid #f0f4f7; padding-top: 10px;">
                        <div class="section-head" style="font-weight: bold; margin-bottom: 8px; color: #8d99a6; text-transform: uppercase; font-size: 11px; letter-spacing: 0.4px;">${section_label}</div>
                        <div class="section-body" style="display: flex; flex-wrap: wrap; gap: 8px;"></div>
                    </div>`).appendTo(dashboard.wrapper);
                }
                
                let $body = $section.find('.section-body');
                $body.empty();
                
                r.message.forEach(doc => {
                    if (doc.doctype === link_doctype) {
                        let badge_color = doc.docstatus === 0 ? '#ff9800' : '#4caf50';
                        let $link = $(`
                            <a href="/app/${doc.doctype.toLowerCase().replace(/ /g, '-')}/${doc.name}" 
                               class="badge-link" 
                               style="display: inline-flex; align-items: center; text-decoration: none; border: 1px solid ${badge_color}; color: ${badge_color}; padding: 3px 10px; border-radius: 16px; font-size: 12px; transition: all 0.2s ease;">
                               <span style="margin-right: 4px;">●</span>
                               <span>${doc.name}</span>
                               <span style="margin-left: 6px; font-size: 10px; opacity: 0.8;">${doc.status}</span>
                            </a>`);
                        
                        $link.hover(
                            function() { $(this).css('background-color', badge_color + '10'); },
                            function() { $(this).css('background-color', 'transparent'); }
                        );
                        
                        $body.append($link);
                    }
                });
            }
        }
    });
};
