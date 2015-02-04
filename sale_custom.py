from datetime import datetime
import time
from openerp.osv import fields, osv
from openerp.addons.sale import sale
from openerp.osv.orm import setup_modifiers
from lxml import etree
from openerp.addons.sale import sale
from openerp.addons.base.res import res_partner
from openerp import netsvc
from openerp.tools.translate import _

class sale_order(osv.osv):
    _inherit = 'sale.order'
    _descrition = 'Sale Order Attachment'
    
   #is_quotation check during the record creation
    def create(self,cr,uid,vals,context=None):
        vals['is_quoatation']=context.get('is_quoatation',False)
        if vals.get('name','/')=='/':
            vals['name'] = self.pool.get('ir.sequence').get(cr, uid, 'sale.order') or '/'
            if vals.get('is_quoatation',False):
                vals['name'] = vals['name'].replace("SO","SQ")
        id = super(sale.sale_order,self).create(cr,uid,vals,context)
        return id
    
    #Allowing users to send mail
    def action_quotation_send(self, cr, uid, ids, context=None):
        '''
        This function opens a window to compose an email, with the edi sale template message loaded by default
        '''
        uid = 1
        assert len(ids) == 1, 'This option should only be used for a single id at a time.'
        ir_model_data = self.pool.get('ir.model.data')
        try:
            template_id = ir_model_data.get_object_reference(cr, uid, 'sale', 'email_template_edi_sale')[1]
        except ValueError:
            template_id = False
        try:
            compose_form_id = ir_model_data.get_object_reference(cr, uid, 'mail', 'email_compose_message_wizard_form')[1]
        except ValueError:
            compose_form_id = False 
        ctx = dict(context)
        ctx.update({
            'default_model': 'sale.order',
            'default_res_id': ids[0],
            'default_use_template': bool(template_id),
            'default_template_id': template_id,
            'default_composition_mode': 'comment',  #removed the "mark_so_as_sent":True so that the state does not change to QUotation sent
            'mark_so_as_sent': True,
        })
        return {
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'views': [(compose_form_id, 'form')],
            'view_id': compose_form_id,
            'target': 'new',
            'context': ctx,
        }

#Allowing users to print the quotation
    def print_quotation(self, cr, uid, ids, context=None):
        '''
        This function prints the sales order and mark it as sent, so that we can see more easily the next step of the workflow
        '''
        uid = 1
        assert len(ids) == 1, 'This option should only be used for a single id at a time'
        datas = {
                 'model': 'sale.order',
                 'ids': ids,
                 'form': self.read(cr, uid, ids[0], context=context),
        }
        return {'type': 'ir.actions.report.xml', 'report_name': 'sale.order', 'datas': datas, 'nodestroy': True}

    def fields_view_get(self, cr, uid, view_id=None, view_type='form', context=None, toolbar=False, submenu=False):
        if context is None:context = {}
        res = super(sale.sale_order, self).fields_view_get(cr, uid,view_id=view_id, view_type=view_type,toolbar=toolbar, submenu=False,context=context)
        doc = etree.XML(res['arch'])
        nodes = doc.xpath("//field[@name='user_id']")
        vals = self.pool.get('res.users').read(cr,uid,uid,['positions'],context)
#         sale_obj = self.pool.get('sale.order').browse(cr,uid,active_id)
#         print "==============================active_id",active_id
        #sale_order_id = self._get_active_id(cr, uid, view_id, context)
#         print "==============================================================active_id",sale_order_id
        
        try:
            if vals.get('positions',False)[0] ==1 or vals.get('positions',False)== False :
                readonly = 1
            else: 
                readonly = 0
            #or try to search for the id using the external id
            for node in nodes:
                node.set('readonly','%s' %readonly)
                node.set('required','1')
                setup_modifiers(node, res['fields']['user_id'])
                res['arch'] = etree.tostring(doc)
        except TypeError:
            readonly = 1
            for node in nodes:
                node.set('readonly','%s' %readonly)
                node.set('required','1')
                setup_modifiers(node, res['fields']['user_id'])
                res['arch'] = etree.tostring(doc)
        nodes = doc.xpath("//field[@name='incoterm']")
        for node in nodes:
            node.set('required','1')
            setup_modifiers(node, res['fields']['incoterm'])
            res['arch'] = etree.tostring(doc)
# Important piece of code
#         if view_type == 'form':
#             trial_arch = res['arch'].split("<sheet>")
#             trial_arch[0]+='''\n         <sheet attrs="{'readonly':[('manager_approval','=','yes')]}" modifiers="{&quot;readonly&quot;: [[&quot;manager_approval&quot;, &quot;=&quot;, &quot;yes&quot;]]}">
#                                          <group attrs="{'readonly':[('manager_approval','=','yes')]}" modifiers="{&quot;readonly&quot;: [[&quot;manager_approval&quot;, &quot;=&quot;, &quot;yes&quot;]]}">'''
#             final_view = trial_arch[0] + trial_arch[1]
#             trial_arch = final_view.split("</sheet>")
#             trial_arch[0]+='''\n       </group>
#                                     </sheet>'''
#             final_view = trial_arch[0] + trial_arch[1]
#             res['arch'] = final_view
#             #res['arch'] = final_view
#             print res['arch'] 
        if context.get('is_quoatation'):
            nodes = doc.xpath("//field[@name='state']")
            for node in nodes:
                node.set('invisible','1')
                setup_modifiers(node, res['fields']['state'])
                res['arch'] = etree.tostring(doc)
            nodes = doc.xpath("//field[@name='packing_detail']")
            for node in nodes:
                node.set('invisible','1')
                setup_modifiers(node, res['fields']['packing_detail'])
                res['arch'] = etree.tostring(doc)
            nodes = doc.xpath("//field[@name='shipping_method']")
            for node in nodes:
                node.set('invisible','1')
                setup_modifiers(node, res['fields']['shipping_method'])
                res['arch'] = etree.tostring(doc)

        return res

    
    def onchange_partner_id(self, cr, uid, ids, part, context=None):
        if not part:
            return {'value': {'partner_invoice_id': False, 'partner_shipping_id': False,  'payment_term': False, 'fiscal_position': False}}

        part = self.pool.get('res.partner').browse(cr, uid, part, context=context)
        addr = self.pool.get('res.partner').address_get(cr, uid, [part.id], ['delivery', 'invoice', 'contact'])
        pricelist = part.property_product_pricelist and part.property_product_pricelist.id or False
        payment_term = part.property_payment_term and part.property_payment_term.id or 1
        fiscal_position = part.property_account_position and part.property_account_position.id or False
        dedicated_salesman = part.user_id and part.user_id.id or uid
        val = {
            'partner_invoice_id': addr['invoice'],
            'partner_shipping_id': addr['delivery'],
            'payment_term': payment_term,
            'fiscal_position': fiscal_position,
            'user_id': dedicated_salesman,
        }
        if pricelist:
            val['pricelist_id'] = pricelist
        print val,context
        return {'value': val,'context':{'oreder_id':"Shivam"}}
    
    def action_cancel(self, cr, uid, ids, context=None):
        if context is None:
            context = {}
        self.write(cr, uid, ids, {'confirm_switch':False})
        super(sale_order,self).action_cancel(cr, uid, ids, context=context)
        return True

    
    def write(self,cr,uid,id,vals,context=None):
        positions = self.pool.get('res.users').read(cr,uid,uid,['positions'],context)
        try:
            manager_approval = self.read(cr,uid,id[0],['manager_approval','state'],context)
        except TypeError:
            manager_approval = self.read(cr,uid,id,['manager_approval','state'],context)
            
        partner_obj = self.pool.get('res.partner')
        if manager_approval.get('manager_approval',False) == 'yes' and manager_approval.get('state',False) == 'draft':
            if vals.get('state',False) == 'manual':
                brw =self.browse(cr,uid,id[0],context)
                #configure if company turn into leads then all the others should also turn into lead autmatically
                if brw.partner_id.lead_check:
                    if brw.partner_id.parent_id:  #meaning if the account is not a company
                         for i in brw.partner_id.parent_id.child_ids:
                             partner_obj.write(cr,uid,i.id,{'customer':True,
                                                               'lead_check':False},context=context)
                             partner_obj.write(cr,uid,brw.partner_id.parent_id.id,{'customer':True,
                                                               'lead_check':False},context=context) 
                    if brw.partner_id.is_company:
                        if brw.partner_id.child_ids:
                            for i in brw.partner_id.child_ids:
                                partner_obj.write(cr,uid,i.id,{'customer':True,
                                                               'lead_check':False},context=context)
                                partner_obj.write(cr,uid,brw.partner_id.id,{'lead_check':False,
                                                                                 'customer':True},context)
                super(sale.sale_order,self).write(cr,uid,id,vals,context=context)
                return True
        if manager_approval.get('manager_approval',False) == 'yes':
            try:
                if positions.get('positions',False)[0] == 1 or positions.get('positions',False) == False and not vals.get('state',False):
                    print "Emloyee trying to edit the approved record"
                    raise osv.except_osv('Update Not allowed','Document Already Approved')
            except TypeError:
                raise osv.except_osv('User Settings','Position Not Alloted')
        super(sale.sale_order,self).write(cr,uid,id,vals,context=context)
        return True
        
    
    def manager_approval_cancel(self,cr,uid,id,context):
        self.write(cr,uid,id,{'manager_approval':'wait'},context)
        return True
    
    def manager_approval(self,cr,uid,id,context):
        self.write(cr,uid,id,{'manager_approval':'yes'},context)
        return True
    
    def _check_company(self,cr,uid,context=None):
		name=self.pool.get('res.company').browse(cr,uid,1).name
		name=name.upper()
		if "RAPID" in name:
			return 14
		if "CAPTHERM" in name:
			return 1
		else :
			return False
    
    _defaults = {
                 'manager_approval':'wait',
                 'order_id': lambda self, cr, uid, context: context.get('order_id', False),
                 'is_quoatation':True,
                 'confirm_switch':False,
                 'incoterm':_check_company,
                 'payment_term':1
                 }
    
    _columns = {
                'packing_detail':fields.char('Packing Deails'),
                'shipping_method':fields.char('Shipping Method'),
                'shipping_status_lines':fields.one2many('sales.shipping.order.status','so_id','Shipping and Packing Status'),
                'manager_approval':fields.selection([('wait','Waiting for Approval'),('yes',"Approved")]),
                'positions':fields.char('Position'),
                'order_id':fields.char("Context Update"),
                'is_quoatation':fields.boolean('Is Quotation'),
                'confirm_switch':fields.boolean('Confirm Switch'),
                'state': fields.selection([
            ('draft', 'Draft Sales Order'),
            ('sent', 'Quotation Sent'),
            ('cancel', 'Cancelled'),
            ('waiting_date', 'Waiting Schedule'),
            ('progress', 'Sales Order'),
            ('manual', 'Confirmed S/O'),
            ('invoice_except', 'Invoice Exception'),
            ('shipping_except','Shipping Exception'),
            ('done', 'Done'),
            ], 'Status', readonly=True, track_visibility='onchange',
            help="Gives the status of the quotation or sales order. \nThe exception status is automatically set when a cancel operation occurs in the processing of a document linked to the sales order. \nThe 'Waiting Schedule' status is set when the invoice is confirmed but waiting for the scheduler to run on the order date.", select=True),

                }

class sale_inv_make_inv(osv.Model):
    _inherit = 'sale.advance.payment.inv'
    _description = "Allow the users to create invoice"
    
    def create_invoices(self, cr, uid, ids, context=None):
        """ create invoices for the active sales orders """
        uid = 1
        sale_obj = self.pool.get('sale.order')
        act_window = self.pool.get('ir.actions.act_window')
        wizard = self.browse(cr, uid, ids[0], context)
        sale_ids = context.get('active_ids', [])
        if wizard.advance_payment_method == 'all':
            # create the final invoices of the active sales orders
            res = sale_obj.manual_invoice(cr, uid, sale_ids, context)
            if context.get('open_invoices', False):
                return res
            return {'type': 'ir.actions.act_window_close'}

        if wizard.advance_payment_method == 'lines':
            # open the list view of sales order lines to invoice
            res = act_window.for_xml_id(cr, uid, 'sale', 'action_order_line_tree2', context)
            res['context'] = {
                'search_default_uninvoiced': 1,
                'search_default_order_id': sale_ids and sale_ids[0] or False,
            }
            return res
        assert wizard.advance_payment_method in ('fixed', 'percentage')

        inv_ids = []
        for sale_id, inv_values in self._prepare_advance_invoice_vals(cr, uid, ids, context=context):
            inv_ids.append(self._create_invoices(cr, uid, inv_values, sale_id, context=context))

        if context.get('open_invoices', False):
            return self.open_invoices( cr, uid, ids, inv_ids, context=context)
        return {'type': 'ir.actions.act_window_close'}

class res_partner_mod(osv.Model):
    _inherit = 'res.partner'
    _description = "Adding Lead Option"
    
    
    ############## changes made by harsh jain for creating pricelist on craetion of a supplier
    def create_pricelist_by_supplier(self,cr,uid,id,vals,context=None):
        if id:
            if type(id) == type([]): id = id[0]
            obj=self.browse(cr,uid,id)
            a1=vals.get('supplier',1)
            if a1==1:
                a1=obj.supplier
            if a1 and obj.is_company and (obj.property_product_pricelist_purchase and obj.property_product_pricelist_purchase.id==2):
                vals_pricelist={'name':obj.name+' Pricelist','active':True,'type':'purchase'}
                id_pricelist=self.pool.get('product.pricelist').create(cr,uid,vals_pricelist,context)
                vals_pricelist_version={'name':obj.name+' version 1','active':True,'pricelist_id':id_pricelist}
                self.pool.get('product.pricelist.version').create(cr,uid,vals_pricelist_version,context)
                return id_pricelist
                
        else:
            if vals.get('is_company') and vals.get('supplier',False):
                vals_pricelist={'name':vals['name']+' Pricelist','active':True,'type':'purchase'}
                id_pricelist=self.pool.get('product.pricelist').create(cr,uid,vals_pricelist,context)
                vals_pricelist_version={'name':vals['name']+' version 1','active':True,'pricelist_id':id_pricelist}
                self.pool.get('product.pricelist.version').create(cr,uid,vals_pricelist_version,context)
                return id_pricelist
        return False    
    ##############################

    
    def write(self,cr,uid,id,vals,context=None):
       
       ############## changes made by harsh jain for creating pricelist on craetion of a supplier
       id_pricelist=self.create_pricelist_by_supplier(cr,uid,id,vals,context)
       if id_pricelist:
           vals['property_product_pricelist_purchase']=id_pricelist
       ###############
       
       if type(id) == type([]): id = id[0]
       if vals.has_key('order_purchase_order'):
           uid = 1
       position = self.pool.get('res.users').read(cr,uid,uid,['positions'],context)
       if position.get('positions',False)[0] == 1 :
           raise osv.except_osv(_('Error!'),_('A purchase user cannot edit the partner information'))
       else:
           res =  super(res_partner.res_partner,self).write(cr,uid,id,vals,context)
           return res    

    def create(self,cr,uid,vals,context):
        if vals.get('is_company',False) == False:
            if vals.get('parent_id',False):
                is_lead = self.pool.get('res.partner').read(cr,uid,vals.get('parent_id',False),['lead_check'],context)
                if is_lead.get('lead_check',False) == True:
                    vals['customer'] = False
                    vals['supplier'] = False
                    vals['lead_check'] = True 
        
        ################# changes made by harsh jain for creating pricelist on craetion of a supplier
        id_check=[]
        id_pricelist=self.create_pricelist_by_supplier(cr,uid,id_check,vals,context)
        if id_pricelist:
            vals['property_product_pricelist_purchase']=id_pricelist
        #################
        
        id = super(res_partner.res_partner,self).create(cr,uid,vals,context)
        return id
    
    def fields_view_get(self, cr, uid, view_id=None, view_type='form', context=None, toolbar=False, submenu=False):
        if context is None:context = {}
        res = super(res_partner.res_partner, self).fields_view_get(cr, uid,view_id=view_id, view_type=view_type,toolbar=toolbar, submenu=False,context=context)
        doc = etree.XML(res['arch'])
        nodes = doc.xpath("//field[@name='user_id']")
        vals = self.pool.get('res.users').read(cr,uid,uid,['positions'],context)
        try:
            if vals.get('positions',False)[0] ==1 or vals.get('positions',False)== False :
                readonly = 1
            else: 
                readonly = 0
            #or try to search for the id using the external id
            for node in nodes:
                node.set('readonly','%s' %readonly)
                setup_modifiers(node, res['fields']['user_id'])
                res['arch'] = etree.tostring(doc)
        except TypeError:
            readonly = 1
            for node in nodes:
                node.set('readonly','%s' %readonly)
                setup_modifiers(node, res['fields']['user_id'])
                res['arch'] = etree.tostring(doc)
        return res

    def  check_lead(self,cr,uid,context):
        if context.has_key('source_create'):
            if context.get('source_create') == 4:
                return True
        else:
            return False
        
    def check_customer(self,cr,uid,context):
        if context.has_key('source_create'):
            if context.get('source_create') == 4:
                return False
        elif context.has_key('search_default_customer'):
            if context.get('search_default_customer') == 1:
                return True
        elif context.has_key('default_customer'):
            if context.get('default_customer') == 1:
                return True
            
    def  check_supplier(self,cr,uid,context):
        if context.has_key('search_default_supplier'):
            if context.get('search_default_supplier') == 1:
                return True
        if context.has_key('default_supplier'):
            if context.get('default_supplier') == 1:
                return True
        else:
            return False    
          
    _defaults = {
                 'date': time.strftime('%Y-%m-%d'),
                 'supplier': check_supplier,
                 'lead_check': check_lead,
                 'customer':False,
                'user_id': lambda self, cr, uid, context: uid,
                 }
    _columns = {
                'lead_check':fields.boolean('Lead'),
               'user_id': fields.many2one('res.users', 'Salesperson', 
               help='The internal user that is in charge of communicating with this contact if any.',
               read=['base.group_sale_salesman','base.group_sale_salesman_all_leads']),
 
                }
