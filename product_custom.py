# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta
import time
from openerp.addons.product import product 
from datetime import date
from datetime import datetime
from openerp import pooler
from openerp.osv import fields, osv
from openerp import tools
from openerp.tools.translate import _
from openerp.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT, DATETIME_FORMATS_MAP, float_compare
import openerp.addons.decimal_precision as dp
from openerp import netsvc
from openerp.addons.sale import sale
from openerp.addons.purchase import purchase
from lxml import etree
from openerp.osv.orm import setup_modifiers
from openerp.addons.mrp import mrp
from openerp import SUPERUSER_ID


class pricelist_partnerinfo(osv.osv):
    _inherit = 'pricelist.partnerinfo'

    _sql_constraints = [
        ('qty_uniq', 'unique(suppinfo_id,min_quantity)', 'The Quantity for each supplier info in the product form must be unique!'),
    ]
    
class product_supplierinfo(osv.osv):
    _inherit = 'product.supplierinfo'
    _description = "product.supplierinfo"
    
    def _check_zero_qty(self,cr,uid,id,context=None):
        cr.execute(
        '''select id,min_quantity,price from pricelist_partnerinfo where suppinfo_id = %s and min_quantity = (select MIN(min_quantity) from pricelist_partnerinfo where suppinfo_id = %s)
        ''' %(id,id))
        
        pricelist_partnerinfo = cr.fetchone()
        if pricelist_partnerinfo:
            pricelist_partnerinfo_obj = self.pool.get('pricelist.partnerinfo')
            if not (pricelist_partnerinfo[1] == 0):
                pricelist_partnerinfo_obj.create(cr,uid,{'suppinfo_id':id,
                                                         'min_quantity':0,
                                                         'price':pricelist_partnerinfo[2]},context=context) 
            else:
                cr.execute(
                '''select id,min_quantity,price from pricelist_partnerinfo where suppinfo_id = %s and price = (select MAX(price) from pricelist_partnerinfo where suppinfo_id = %s)
                ''' %(id,id))
                price = cr.fetchone()
                pricelist_partnerinfo_obj.write(cr,uid,pricelist_partnerinfo[0],{'price':price[2]},context)        
        return True
    
    def write(self,cr,uid,ids,vals,context=None):
        if type(ids) == type(1):ids = [ids]
        for id in ids:
            result = super(product_supplierinfo,self).write(cr,uid,id,vals,context)
            self._check_zero_qty(cr,uid,id,context)
        return result
   
    def create(self,cr,uid,vals,context=None):
        id = super(product_supplierinfo,self).create(cr,uid,vals,context)
        self._check_zero_qty(cr,uid,id,context)
        return id
    
class stock_warehouse_orderpoint(osv.osv):
    _inherit = "stock.warehouse.orderpoint"
    _description = "addoning man2one field"
    _columns = {
                'connect_product':fields.many2one('product.product','Connector'),
                }
    
class sales_shipping_order_status(osv.osv):
    _name="sales.shipping.order.status"
    _description = "Shipping Order Status"
    _columns={
               'so_id':fields.many2one('sale.order',invisible=True),
                'order_status':fields.selection([('await','Await Production Completion'),('ready','Ready To Ship'),
                                 ('date_confirmed','Shipping Date Confirmed'),('on_route','Shipment on Route'),
                             ('pending','Shipment Pending'),('received','Shipment Received'),
                             ('cancel','Shipment Canceled')],
                            'Shipping Status'),
                'date':fields.date('Date'),
               
               }

class shipping_order_status(osv.osv):
    _name="shipping.order.status"
    _description = "Shipping Order Status"
    _columns={
               'po_id':fields.many2one('purchase.order',invisible=True),
                'order_status':fields.selection([('await','Await Production Completion'),('ready','Ready To Ship'),
                                 ('date_confirmed','Shipping Date Confirmed'),('on_route','Shipment on Route'),
                             ('pending','Shipment Pending'),('received','Shipment Received'),
                             ('cancel','Shipment Canceled')],
                            'Shipping Status'),
                'date':fields.date('Date'),
               
               }
    
class order_production_stuatus(osv.osv):
    _name="order.production.status"
    _description = "Production Order Status"
    _columns = {
                'po_id':fields.many2one('purchase.order',invisible=True),
                'order_status':fields.selection([('pending','Pending Production'),('in_production','In Production'),
                                 ('production_delayed','Production Delayed'),('awaiting','Await Quality Inspection'),
                             ('approved','Quality Inspection Approved'),('failed','Quality Inspection Failed'),
                             ('complete','Production Complete'),('cancel','Production Canceled')],
                            'Production Status'),
                'date':fields.date('Date'),
                }


class sale_order_modified(osv.osv):
    _inherit='sale.order'
    _description = "Adding history lines"
    
    def _check_attachment(self,cr,uid,ids,context=None):
        attachment_line = self.read(cr,uid,ids,['order_line'],context)
        for i in attachment_line:
            if i.get('order_line',False) :
                return True
            else:
                return False

    _constraints = [(_check_attachment, 'You have entered any order line', ['order_line'])]
    
    
    def action_button_confirm(self, cr, uid, ids, context=None):
        uid = SUPERUSER_ID
        self.write(cr,uid,ids,{'confirm_switch':True},context)
        if context.get('is_quoatation',False): 
            name = self.read(cr,uid,ids[0],['name'],context)
            name['name'] = name.get('name',False).replace('SQ','SO')
            id = []
            assert len(ids) == 1, 'This option should only be used for a single id at a time.'
            id.append(self.copy(cr,uid,ids[0],context))
            self.write(cr,uid,id[0],{'is_quoatation':False},context)
            wf_service = netsvc.LocalService('workflow')
            wf_service.trg_validate(uid, 'sale.order', id[0], 'order_confirm', cr)
            self.write(cr,uid,id,{'name':name['name'],'state':'manual'},context)
            # redisplay the record as a sales order
        vals = self.read(cr,uid,ids[0],['partner_id'],context)
        obj =self.pool.get('res.partner')
        obj.write(cr,uid,vals['partner_id'][0],{'order_line_customer':[(4,ids[0])]},context=context)
        assert len(ids) == 1, 'This option should only be used for a single id at a time.'
        if not context.get('is_quoatation',False) :
            wf_service = netsvc.LocalService('workflow')
            wf_service.trg_validate(uid, 'sale.order', ids[0], 'order_confirm', cr)
        obj_order = self.pool.get('sale.order').browse(cr,uid,ids[0],context)
        obj_brw = obj.browse(cr,uid,vals['partner_id'][0],context)
        indicator = 0 
        # redisplay the record as a sales order
        view_ref = self.pool.get('ir.model.data').get_object_reference(cr, uid, 'sale', 'view_order_form')
        view_id = view_ref and view_ref[1] or False,
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sales Order'),
            'res_model': 'sale.order',
            'res_id': ids[0],
            'view_type': 'form',
            'view_mode': 'form',
            'view_id': view_id,
            'target': 'current',
            'nodestroy': True,
        }
        
class mrp_bom(osv.osv):
    _inherit = "mrp.bom"
    _description= "making bom_lines mandatory"
    
    def create(self,cr,uid,vals,context):
        custom_sequence = self.pool.get('ir.sequence').get(cr, uid, 'mrp.bom.captherm')
        vals['code'] = custom_sequence
        id = super(mrp.mrp_bom,self).create(cr,uid,vals,context)
        return id
            
class product_product(osv.osv):
    _inherit="product.product"
    _description = "Inserting the Reordering Line"
    _order = "part_no"
    _sql_constraints = [ 
        ('unique_part_no', 'unique(part_no)', 'Part No. should be unique!'), 
    ]
    
    
    def form_view_open(self,cr,uid,id,context=None):
       
        view_ref = self.pool.get('ir.model.data').get_object_reference(cr, uid, 'product', 'product_normal_form_view')
        view_id = view_ref and view_ref[1] or False,
        return {
            'type': 'ir.actions.act_window',
            'res_model':'product.product',
            'res_id':id[0],
            'view_type': 'form',
            'view_mode': 'form',
            'view_id': view_id,
            'target': 'current',
            
        }
        
        
    def _check_line_ids(self,cr,uid,ids,context=None):
        line_ids = self.browse(cr,uid,id,context).line_ids
        if line_ids ==None:
            return True
        if len(line_ids) > 1:
            return False
        return True
    
    _constraints = [(_check_line_ids, 'You have already associated a reordering rule with this product', ['line_ids'])]
    
    def fields_view_get(self, cr, uid, view_id=None, view_type='form', context=None, toolbar=False, submenu=False):
        if context is None:context = {}
        res = super(product.product_product, self).fields_view_get(cr, uid, view_id=view_id, view_type=view_type, context=context, toolbar=toolbar, submenu=False)
        doc = etree.XML(res['arch'])
        vals = self.pool.get('res.users').read(cr,uid,uid,['positions'],context)
        nodes = doc.xpath("//field[@name='active']")
        for node in nodes:
            node.set('readonly','1')
            setup_modifiers(node, res['fields']['active'])
            res['arch'] = etree.tostring(doc)
        nodes = doc.xpath("//field[@name='produce_delay']")
        for node in nodes:
            node.set('required','1')
            setup_modifiers(node, res['fields']['produce_delay'])
            res['arch'] = etree.tostring(doc)
        return res

    def manager_approval_cancel(self,cr,uid,id,context):
        self.write(cr,uid,id,{'manager_approval':'no','active':False},context)
        return True

    def manager_approval(self,cr,uid,id,context):
        self.write(cr,uid,id,{'manager_approval':'yes','active':True},context)
        return True
    
    def flag_update(self,cr,uid,id,context):
        self.write(cr,uid,id,{'flag':1},context)
        return True

    def update_image_flag(self,cr,uid,id,context):
        self.write(cr,uid,id,{'image_flag':1,'check1':False,
                              'check2':False,
                              'check3':False,
                              'check4':False},context)
        
        return True
    
    def on_change_image(self,cr,uid,id,check,onchange_flag,context=None):
        """ Display the binary from ir.attachment, if already exist """
        if check == False:
            if onchange_flag == 0:
                return {'value':{'onchange_flag':1}}
            return {'value':{'onchange_flag':0,
                             'check1':False,
                             'check2':False,
                             'check3':False,
                             'check4':False}}
        if check == True:
            if context.get('source',False) == 1:
                try:
                    image = self.read(cr,uid,id,['image_small'],context)[0]
                except IndexError:
                    print "The Record is being created"
                try:
                     return {'value':{'image_final':image['image_small'],'check2':False,'check3':False,
                                 'check4':False,'onchange_flag':0}}
                except UnboundLocalError:
                     print "The product is new"
    
            if context.get('source',False) == 2:
                image = self.read(cr,uid,id,['image2'],context)[0]
                trial = tools.image_get_resized_images(image['image2'], avoid_resize_medium=True)
                image['image2'] = tools.image_resize_image_big(trial['image_medium'])
                return {'value':{'image_final':image['image2'],'check1':False,'check3':False,'check4':False,
                                 'onchange_flag':0}}
            if context.get('source',False) == 3:
                image = self.read(cr,uid,id,['image3'],context)[0]
                image['image3'] = tools.image_resize_image_big(image['image3'])
                return {'value':{'image_final':image['image3'],'check1':False,'check2':False,'check4':False,
                                 'onchange_flag':0}}
            if context.get('source',False) == 4:
                image = self.read(cr,uid,id,['image4'],context)[0]
                image['image4'] = tools.image_resize_image_big(image['image4'])
                return {'value':{'image_final':image['image4'],'check1':False,'check2':False,'check3':False,
                                 'onchange_flag':0}}
                
    def get_product_available_month(self, cr, uid, ids, context=None):
        """ Finds whether product is available or not in particular warehouse.
        @return: Dictionary of values
        """
        if context is None:
            context = {}
        location_obj = self.pool.get('stock.location')
        warehouse_obj = self.pool.get('stock.warehouse')
        shop_obj = self.pool.get('sale.shop')
        
        states = context.get('states',[])
        what = context.get('what',())
        if not ids:
            ids = self.search(cr, uid, [])
        res = {}.fromkeys(ids, 0.0)
        if not ids:
            return res

        if context.get('shop', False):
            warehouse_id = shop_obj.read(cr, uid, int(context['shop']), ['warehouse_id'])['warehouse_id'][0]
            if warehouse_id:
                context['warehouse'] = warehouse_id

        if context.get('warehouse', False):
            lot_id = warehouse_obj.read(cr, uid, int(context['warehouse']), ['lot_stock_id'])['lot_stock_id'][0]
            if lot_id:
                context['location'] = lot_id

        if context.get('location', False):
            if type(context['location']) == type(1):
                location_ids = [context['location']]
            elif type(context['location']) in (type(''), type(u'')):
                location_ids = location_obj.search(cr, uid, [('name','ilike',context['location'])], context=context)
            else:
                location_ids = context['location']
        else:
            location_ids = []
            wids = warehouse_obj.search(cr, uid, [], context=context)
            if not wids:
                return res
            for w in warehouse_obj.browse(cr, uid, wids, context=context):
                location_ids.append(w.lot_stock_id.id)

        # build the list of ids of children of the location given by id
        if context.get('compute_child',True):
            child_location_ids = location_obj.search(cr, uid, [('location_id', 'child_of', location_ids)])
            location_ids = child_location_ids or location_ids
        
        # this will be a dictionary of the product UoM by product id
        product2uom = {}
        uom_ids = []
        for product in self.read(cr, uid, ids, ['uom_id'], context=context):
            product2uom[product['id']] = product['uom_id'][0]
            uom_ids.append(product['uom_id'][0])
        # this will be a dictionary of the UoM resources we need for conversion purposes, by UoM id
        uoms_o = {}
        for uom in self.pool.get('product.uom').browse(cr, uid, uom_ids, context=context):
            uoms_o[uom.id] = uom

        results = []
        results2 = []
        from_date=context.get('from_date',False)
        to_date = context.get('to_date',False)
        date_str = False
        date_values = False
        where = [tuple(location_ids),tuple(location_ids),tuple(ids),tuple(states)]
        if from_date and to_date:
            date_str = "date_expected>=%s and date_expected<=%s"
            where.append(tuple([from_date]))
            where.append(tuple([to_date]))
        elif from_date:
            date_str = "date_expected>=%s"
            date_values = [from_date]
        elif to_date:
            date_str = "date_expected<=%s"
            date_values = [to_date]
        if date_values:
            where.append(tuple(date_values))

        prodlot_id = context.get('prodlot_id', False)
        prodlot_clause = ''
        if prodlot_id:
            prodlot_clause = ' and prodlot_id = %s '
            where += [prodlot_id]
        # TODO: perhaps merge in one query.
        if 'in' in what:
            # all moves from a location out of the set to a location in the set
            cr.execute(
                'select sum(product_qty), product_id, product_uom '\
                'from stock_move '\
                'where location_id NOT IN %s '\
                'and location_dest_id IN %s '\
                'and product_id IN %s '\
                'and state IN %s ' + (date_str and 'and '+date_str+' ' or '') +' '\
                + prodlot_clause + 
                'group by product_id,product_uom',tuple(where))
            results = cr.fetchall()
        if 'out' in what:
            # all moves from a location in the set to a location out of the set
            cr.execute(
                'select sum(product_qty), product_id, product_uom '\
                'from stock_move '\
                'where location_id IN %s '\
                'and location_dest_id NOT IN %s '\
                'and product_id  IN %s '\
                'and state in %s ' + (date_str and 'and '+date_str+' ' or '') + ' '\
                + prodlot_clause + 
                'group by product_id,product_uom',tuple(where))
            results2 = cr.fetchall()
            
        # Get the missing UoM resources
        uom_obj = self.pool.get('product.uom')
        uoms = map(lambda x: x[2], results) + map(lambda x: x[2], results2)
        if context.get('uom', False):
            uoms += [context['uom']]
        uoms = filter(lambda x: x not in uoms_o.keys(), uoms)
        if uoms:
            uoms = uom_obj.browse(cr, uid, list(set(uoms)), context=context)
            for o in uoms:
                uoms_o[o.id] = o
                
        #TOCHECK: before change uom of product, stock move line are in old uom.
        context.update({'raise-exception': False})
        # Count the incoming quantities
        for amount, prod_id, prod_uom in results:
            amount = uom_obj._compute_qty_obj(cr, uid, uoms_o[prod_uom], amount,
                     uoms_o[context.get('uom', False) or product2uom[prod_id]], context=context)
            res[prod_id] += amount
        # Count the outgoing quantities
        for amount, prod_id, prod_uom in results2:
            amount = uom_obj._compute_qty_obj(cr, uid, uoms_o[prod_uom], amount,
                    uoms_o[context.get('uom', False) or product2uom[prod_id]], context=context)
            res[prod_id] -= amount
        return res

    def _product_available_month(self, cr, uid, ids, field_names=None, arg=False, context=None):
        """ Finds the incoming and outgoing quantity of product.
        @return: Dictionary of values
        """
        if not field_names:
            field_names = []
        if context is None:
            context = {}
        res = {}
        to_date = str(date.today() + relativedelta( months = +3 ))
        context.update({'to_date':to_date})
        for id in ids:
            res[id] = {}.fromkeys(field_names, 0.0)
        c = context.copy()
        c.update({ 'states': ('confirmed','waiting','assigned','done'), 'what': ('in', 'out') })
        stock = self.get_product_available_month(cr, uid, ids, context=c)
        for id in ids:
            res[id]['virtual_available_months'] = stock.get(id, 0.0)
        return res


    def _customer_ids(self, cr, uid, ids, name, arg, context=None):
        res = {}
        for id in ids:
            list = []
            cr.execute('''
            select distinct partner_id from sale_order_line 
            left join sale_order on sale_order_line.order_id = sale_order.id 
            where product_id = %s; 
             ''' %(id))
            for i in cr.fetchall():
                list.append(i[0])
            res.update({id:list})
        return res
        
    _columns = {
                'customer_lines':fields.function (_customer_ids,relation ='res.partner',string = "Customers",method=True,type='many2many'),
                'onchange_flag':fields.integer('OnchangeFlag'),
                'image_final':fields.binary('Product Image'),
                'part_no':fields.char('Engineering P/N'),
                'line_ids':fields.one2many('stock.warehouse.orderpoint','connect_product','Reordering Rules'),
                'flag':fields.integer('flag'),
                'image_flag':fields.integer('Image flag'),
                'virtual_available_months': fields.function(_product_available_month, multi='virtual_available_months',
            type='float',  digits_compute=dp.get_precision('Product Unit of Measure'),
            string='Next three months Forecasted Quantity',
            help="Forecast quantity for next three months (computed as Quantity On Hand "
                 "- Outgoing + Incoming)\n"
                 "In a context with a single Stock Location, this includes "
                 "goods stored in this location, or any of its children.\n"
                 "In a context with a single Warehouse, this includes "
                 "goods stored in the Stock Location of this Warehouse, or any "
                 "of its children.\n"
                 "In a context with a single Shop, this includes goods "
                 "stored in the Stock Location of the Warehouse of this Shop, "
                 "or any of its children.\n"
                 "Otherwise, this includes goods stored in any Stock Location "
                 "with 'internal' type."),
                'check1':fields.boolean('Check 1'),
                'check2':fields.boolean('Check 2'),
                'check3':fields.boolean('Check3'),
                'check4':fields.boolean('Check4'),
                'image2':fields.binary('image2'),
                'image3':fields.binary('image3'),
                'image4':fields.binary('image4'),
                'manager_approval':fields.selection([('no','Waiting Approval'),('yes','Approved')],'Manager Approval'),
                'active': fields.boolean('Active', help="If unchecked, it will allow you to hide the product without removing it.",
                                         ),
                }
    _defaults = {
                 'type':'product',
                 'procure_method':'make_to_stock',
                 'manager_approval':'no',
                 'flag':0,
                 'image_flag':0,
                 'onchange_flag':1,
                 'active':False,
                 }
    
class res_partner(osv.osv):
    _inherit='res.partner'
    _description="Adding PO SO order line"
    
    _defaults = {
                 'property_product_pricelist_purchase':0,
                 }
    def _get_rfq(self,cr,uid,ids,name,args,context=None):
        res = {}
        if name == 'order_line_supplier':
            for id in ids:
                list = []
                cr.execute('''
                select id from purchase_order where source_create = 1 and partner_id = %s
                ''' %(id))
                for rfq in cr.fetchall():
                    list.append(rfq[0])
                res.update({id:list})
        return res
    
    def _get_purchase_order(self,cr,uid,ids,name,args,context=None):
        res = {}
        if name == 'order_purchase_order':
            for id in ids:
                list = []
                cr.execute('''
                select id from purchase_order where source_create <> 1 and partner_id = %s
                ''' %(id))
                for rfq in cr.fetchall():
                    list.append(rfq[0])
                res.update({id:list})
        return res

    def _get_sale_order(self,cr,uid,ids,name,args,context=None):
        res = {}
        if name == 'order_line_customer':
            for id in ids:
                list = []
                cr.execute('''
                select id from sale_order where is_quoatation=False and partner_id = %s
                ''' %(id))
                for rfq in cr.fetchall():
                    list.append(rfq[0])
                res.update({id:list})
        return res
    
    def _get_quote(self,cr,uid,ids,name,args,context=None):                
        res = {}
        if name == 'quote_history':
            for id in ids:
                list = []
                cr.execute('''
                select id from sale_order where is_quoatation=True and partner_id = %s
                ''' %(id))
                for rfq in cr.fetchall():
                    list.append(rfq[0])
                res.update({id:list})            
        return res    
    
    _columns={
              'order_purchase_order':fields.function(_get_purchase_order,method=True,type='many2many',relation="purchase.order",string="Purchase Order History"),
              'order_line_supplier':fields.function(_get_rfq,method=True,type='many2many',relation="purchase.order",string="RFQ History"),
            'order_line_customer':fields.function(_get_sale_order,method=True,type='many2many',relation="sale.order",string="RFQ History"),
            'quote_history':fields.function(_get_quote,method=True,type='many2many',relation="sale.order",string="RFQ History"),
             'property_product_pricelist_purchase': fields.property(
          'product.pricelist',
          type='many2one', 
          relation='product.pricelist', 
          domain=[('type','=','purchase')],
          string="Purchase Pricelist", 
          view_load=True,
          help="This pricelist will be used, instead of the default one, for purchases from the current partner"),

              }

class purchase_order_line(osv.osv):
    _inherit = "purchase.order.line"
    _description = "Onchange Functionality"

    def onchange_product_id(self, cr, uid, ids, pricelist_id, product_id, qty, uom_id,
            partner_id, date_order=False, fiscal_position_id=False, date_planned=False,
            name=False, price_unit=False, context=None):
        """
        onchange handler of product_id.
        """
        
        print "**********************************"
        if context is None:
            context = {}

        res = {'value': {'price_unit': price_unit or 0.0, 'name': name or '', 'product_uom' : uom_id or False}}
        if not product_id:
            return res

        product_product = self.pool.get('product.product')
        product_uom = self.pool.get('product.uom')
        res_partner = self.pool.get('res.partner')
        product_supplierinfo = self.pool.get('product.supplierinfo')
        product_pricelist = self.pool.get('product.pricelist')
        account_fiscal_position = self.pool.get('account.fiscal.position')
        account_tax = self.pool.get('account.tax')

        # - check for the presence of partner_id and pricelist_id
        #if not partner_id:
        #    raise osv.except_osv(_('No Partner!'), _('Select a partner in purchase order to choose a product.'))
        #if not pricelist_id:
        #    raise osv.except_osv(_('No Pricelist !'), _('Select a price list in the purchase order form before choosing a product.'))

        # - determine name and notes based on product in partner lang.
        context_partner = context.copy()
        if partner_id:
            partner_obj = res_partner.browse(cr, uid, partner_id)
            lang = partner_obj.lang
            if not (partner_obj.is_company):
                if partner_obj.parent_id:
                    print "====================================11111111111111111111111111111111111",partner_obj.parent_id.id
                    partner_id = partner_obj.parent_id.id
            context_partner.update( {'lang': lang, 'partner_id': partner_id} )
        product = product_product.browse(cr, uid, product_id, context=context_partner)
        #call name_get() with partner in the context to eventually match name and description in the seller_ids field
        dummy, name = product_product.name_get(cr, uid, product_id, context=context_partner)[0]
        if product.description_purchase:
            name += '\n' + product.description_purchase
        res['value'].update({'name': name})

        # - set a domain on product_uom
        res['domain'] = {'product_uom': [('category_id','=',product.uom_id.category_id.id)]}

        # - check that uom and product uom belong to the same category
        product_uom_po_id = product.uom_po_id.id
        if not uom_id:
            uom_id = product_uom_po_id

        if product.uom_id.category_id.id != product_uom.browse(cr, uid, uom_id, context=context).category_id.id:
            if self._check_product_uom_group(cr, uid, context=context):
                res['warning'] = {'title': _('Warning!'), 'message': _('Selected Unit of Measure does not belong to the same category as the product Unit of Measure.')}
            uom_id = product_uom_po_id

        res['value'].update({'product_uom': uom_id})

        # - determine product_qty and date_planned based on seller info
        if not date_order:
            date_order = fields.date.context_today(self,cr,uid,context=context)


        supplierinfo = False
        for supplier in product.seller_ids:
            if partner_id and (supplier.name.id == partner_id):
                supplierinfo = supplier
                if supplierinfo.product_uom.id != uom_id:
                    res['warning'] = {'title': _('Warning!'), 'message': _('The selected supplier only sells this product by %s') % supplierinfo.product_uom.name }
                min_qty = product_uom._compute_qty(cr, uid, supplierinfo.product_uom.id, supplierinfo.min_qty, to_uom_id=uom_id)
                if (qty or 0.0) < min_qty: # If the supplier quantity is greater than entered from user, set minimal.
                    if qty:
                        res['warning'] = {'title': _('Warning!'), 'message': _('The selected supplier has a minimal quantity set to %s %s, you should not purchase less.') % (supplierinfo.min_qty, supplierinfo.product_uom.name)}
                    qty = min_qty
        dt = self._get_date_planned(cr, uid, supplierinfo, date_order, context=context).strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        qty = qty or 1.0
        res['value'].update({'date_planned': date_planned or dt})
        if qty:
            res['value'].update({'product_qty': qty})

        # - determine price_unit and taxes_id
        if pricelist_id:
            price = product_pricelist.price_get(cr, uid, [pricelist_id],
                    product.id, qty or 1.0, partner_id or False, {'uom': uom_id, 'date': date_order})[pricelist_id]
        else:
            price = product.standard_price

        taxes = account_tax.browse(cr, uid, map(lambda x: x.id, product.supplier_taxes_id))
        fpos = fiscal_position_id and account_fiscal_position.browse(cr, uid, fiscal_position_id, context=context) or False
        taxes_ids = account_fiscal_position.map_tax(cr, uid, fpos, taxes)
        res['value'].update({'price_unit': price, 'taxes_id': taxes_ids})

        return res    
    
class purchase_order_modified(osv.osv):
    _inherit='purchase.order'
    _description = "Change the method"
    
    
    def _order_lines_for_refresh(self, cr, uid, ids, context={}):
        for id in ids:
            obj = self.pool.get('purchase.order.line')
            cr.execute('''
            select product_id from purchase_order_line where order_id = %s and refresh_prices = True
            ''' %(id))
            list = []
            for i in cr.fetchall():
                list.append(i[0])
            if not (len(list) == len(set(list))):
                return False
        return True

    _constraints = [
        (_order_lines_for_refresh, 'Error! Cannot have two  purchase order line with same products refresh the same supplier info in the product form', ['order_line']),
    ]



    def onchange_partner_id(self, cr, uid, ids, partner_id,context=None):
        partner = self.pool.get('res.partner')
        if not partner_id:
            return {'value': {
                'fiscal_position': False,
                'payment_term_id': False,
                }}
        supplier_address = partner.address_get(cr, uid, [partner_id], ['default'])
        supplier = partner.browse(cr, uid, partner_id)
        # ############changes made by harsh jain to include pricelist 
        if supplier.is_company:
            return {'value': {
            'pricelist_id':supplier.property_product_pricelist_purchase and supplier.property_product_pricelist_purchase.id or False,
            'fiscal_position': supplier.property_account_position and supplier.property_account_position.id or False,
            'payment_term_id': supplier.property_supplier_payment_term and supplier.property_supplier_payment_term.id or False,
            }}
        else:
            return {'value': {
            'pricelist_id':(supplier.parent_id.property_product_pricelist_purchase and  supplier.parent_id.property_product_pricelist_purchase.id) or supplier.property_product_pricelist_purchase.id or False,
            'fiscal_position': (supplier.parent_id.property_account_position and supplier.parent_id.property_account_position.id) or (supplier.property_account_position and supplier.property_account_position.id) or False,
            'payment_term_id': (supplier.parent_id.property_supplier_payment_term and supplier.parent_id.property_supplier_payment_term.id) or supplier.property_supplier_payment_term.id or False,
            }}
    

    

    def view_picking(self, cr, uid, ids, context=None):
        '''
        This function returns an action that display existing pîcking orders of given purchase order ids.
        '''
        mod_obj = self.pool.get('ir.model.data')
        pick_ids = []
        for po in self.browse(cr, uid, ids, context=context):
            pick_ids += [picking.id for picking in po.picking_ids]

        action_model, action_id = tuple(mod_obj.get_object_reference(cr, uid, 'stock', 'action_picking_tree4'))
        action = self.pool.get(action_model).read(cr, uid, action_id, context=context)
        ctx = eval(action['context'])
        ctx.update({
            'search_default_purchase_id': ids[0]
        })
        if pick_ids and len(pick_ids) == 1:
            form_view_ids = [view_id for view_id, view in action['views'] if view == 'form']
            view_id = form_view_ids and form_view_ids[0] or False
            action.update({
                'views': [],
                'view_mode': 'form',
                'view_id': view_id,
                'res_id': pick_ids[0]
            })

        action.update({
            'context': ctx,
        })
        return action

    def creates_purchase_confirm(self, cr, uid, ids, context=None):
        uid = SUPERUSER_ID
        po = self.browse(cr,uid,ids[0],context) 
        ir_model_data = self.pool.get('ir.model.data')
        view_id = ir_model_data.get_object_reference(cr, uid, 'captherm', 'purchase_order_form_modified_actual')[1]
        if "RFQ" in po.name:
            name = po.name.replace("RFQ","PO")
            context.update({'source_create':3})
            id = self.copy(cr,uid,po.id,{'name':name,'origin':po.name or '','minimum_planned_date':False,'date_order':time.strftime('%Y-%m-%d'),'manager_approval':'no','source_create':3,'state':'draft'},context)
        
        return {
                'view_type': 'form',
                "view_mode": 'form',
                'res_model': 'purchase.order',
                'type': 'ir.actions.act_window',
                'view_id' : view_id,
                'res_id':id,
                'target': 'current',
                'context':context
               }                                        

    def wkf_send_rfq(self, cr, uid, ids, context=None):
        '''
        This function opens a window to compose an email, with the edi purchase template message loaded by default
        '''
        uid =1
        ir_model_data = self.pool.get('ir.model.data')
        try:
            template_id = ir_model_data.get_object_reference(cr, uid, 'purchase', 'email_template_edi_purchase')[1]
        except ValueError:
            template_id = False
        try:
            compose_form_id = ir_model_data.get_object_reference(cr, uid, 'mail', 'email_compose_message_wizard_form')[1]
        except ValueError:
            compose_form_id = False 
        ctx = dict(context)
        ctx.update({
            'default_model': 'purchase.order',
            'default_res_id': ids[0],
            'default_use_template': bool(template_id),
            'default_template_id': template_id,
            'default_composition_mode': 'comment',
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

    def cancel_manager_approval(self,cr,uid,id,context=None):
        self.write(cr,uid,id,{'manager_approval':'no'},context)
        return True

    def confirm_manager_approval(self,cr,uid,id,context=None):
        self.write(cr,uid,id,{'manager_approval':'yes'},context)
        return True
    
    def create(self, cr, uid, vals, context=None):
        try:
            vals['source_create'] = context.get('source_create',False)
        except KeyError:
            vals['source_create'] = context.get('source_create',False)
        if context.get('source_create',False) == 1 or context.get('source_create',False) == 3:
            vals['scheduler']=True
        if vals.get('name','/')=='/':
            vals['name'] = self.pool.get('ir.sequence').get(cr, uid, 'purchase.order') or '/'
            if context.get('source_create',False) == 1:
                vals['name']= vals['name'].replace('PO','RFQ')
        return super(purchase.purchase_order, self).create(cr, uid, vals, context=context)
    
    def write(self,cr,uid,id,vals,context=None):
        if context == None:context={}
        
        if vals.get('state',False) or vals.get('invoice_ids',False): 
            uid=1
            context.update({
                            'flag':1
                            })
        try:
            approval = self.pool.get('purchase.order').read(cr,1,id[0],['manager_approval'],context)
            if approval.get('manager_approval',False) == 'yes' or approval.get('manager_approval',False) == False:
                position = self.pool.get('res.users').read(cr,1,uid,['positions'],context)
                if position.get('positions')[0] == 1 and vals.get('state',False) not in ['sent']:
                     raise osv.except_osv('Update Not allowed','Document Already Approved or Super Administrator not set')
        except TypeError:
            print "Type Error Averted"
            
        super(purchase.purchase_order,self).write(cr,uid,id,vals,context=context)
        return True
    
    
    def cofirm_rfq_mod(self,cr,uid,ids,context=None):
        pricelist_partnerinfo = self.pool.get('pricelist.partnerinfo')
        product_supplierinfo = self.pool.get('product.supplierinfo')
        product_pricelist_item = self.pool.get('product.pricelist.item')
        for purchase_order in self.browse(cr,uid,ids,context):
            for order_line in purchase_order.order_line:
                flag = True
                cr.execute('''
                    select name,id from product_supplierinfo where product_id = %s
                ''' %(order_line.product_id.id))
                for supplier in cr.fetchall():
                    if supplier[0] == purchase_order.partner_id.id:
                        if order_line.refresh_prices:
                            product_supplierinfo.write(cr,uid,supplier[1],{'min_qty':order_line.product_qty},context)
                            cr.execute('''
                            delete from pricelist_partnerinfo where suppinfo_id = %s
                            ''' %(supplier[1]))
                            
                            product_supplierinfo.write(cr,uid,supplier[1],{
                                                                           'pricelist_ids':[(0,0,{
                                                                 'min_quantity':order_line.product_qty,
                                                                 'price':order_line.price_unit})]
                                                                 },context)
 
                        else:
                            cr.execute('''
                            select id from pricelist_partnerinfo where suppinfo_id = %s and min_quantity = %s 
                            ''' %(supplier[1],order_line.product_qty))
                            
                            for line in cr.fetchall():
                                flag = False 
                                cr.execute('''
                                update pricelist_partnerinfo set price = %s where id = %s
                                ''' %(order_line.price_unit,line[0]))
                            if flag:
                                product_supplierinfo.write(cr,uid,supplier[1],{'pricelist_ids':[(0,0,{
                                                                 'min_quantity':order_line.product_qty,
                                                                 'price':order_line.price_unit,})]
                                                                 },context)
            #update pricelist
            cr.execute('''
                select v.id,i.id from product_pricelist as p  left join product_pricelist_version as v on p.id= v.pricelist_id left join product_pricelist_item i on v.id = i.price_version_id where i.product_id = %s and p.id =%s and v.active=true  
            ''' %(order_line.product_id.id,purchase_order.pricelist_id.id))
            
            if not cr.fetchall():
                cr.execute('''
                select v.id from product_pricelist as p  left join product_pricelist_version as v on p.id= v.pricelist_id  where p.id =%s and v.active=true    
            ''' %(purchase_order.pricelist_id.id))
                for i in cr.fetchall():
                    product_pricelist_item.create(cr,uid,{
                                                             'product_id':order_line.product_id.id,
                                                             'base':-2,
                                                             'price_version_id':i[0]
                                                             },context)                    
            self.write(cr,uid,purchase_order.id,{'state_rfq':'yes'},context)        
        
        return True

    
    def fields_view_get(self, cr, uid, view_id=None, view_type='form', context=None, toolbar=False, submenu=False):
        if context is None:context = {}
        res = super(purchase.purchase_order, self).fields_view_get(cr, uid, view_id=view_id, view_type=view_type, context=context, toolbar=toolbar, submenu=False)
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
    STATE_SELECTION = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('confirmed', 'Waiting Approval'),
        ('approved', 'Confirmed Purchase Order'),
        ('except_picking', 'Shipping Exception'),
        ('except_invoice', 'Invoice Exception'),
        ('done', 'Done'),
        ('cancel', 'Cancelled')
    ]


    _columns ={
                  'state': fields.selection(STATE_SELECTION, 'Status', readonly=True, help="The status of the purchase order or the quotation request. A quotation is a purchase order in a 'Draft' status. Then the order has to be confirmed by the user, the status switch to 'Confirmed'. Then the supplier must confirm the order to change the status to 'Approved'. When the purchase order is paid and received, the status becomes 'Done'. If a cancel action occurs in the invoice or in the reception of goods, the status becomes in exception.", select=True),
                  'shipping_detail':fields.char('Shipping Detail'),
                  'packing_method':fields.char('Packing Method'),
                  'state_rfq':fields.selection([('no','Unconfirmed'),('yes','Confirmed')]),
                  'scheduler':fields.boolean('Scheduler Source'),
                  'manager_approval':fields.selection([('no','Waiting for Approval'),('yes','Approved')],'Status'),
                  'user_id':fields.many2one('res.users','Purchase Person'),
                  'source_create':fields.integer('Source of Creation'),
                  'active':fields.boolean('Active'),
                  'ship_status_lines':fields.one2many('shipping.order.status','po_id','Supplier Shipping Status'),
                  'prod_status_lines':fields.one2many('order.production.status','po_id','Supplier Production History'),
                  'quality_standard':fields.char('Quality Control Standard'), 
                   }
    _defaults = {
                 'active': lambda *a: 1,
                 'state_rfq':'no',
                 'scheduler':False,
                 'manager_approval':'no',
                 'user_id':lambda self, cr, uid, context: uid, 
                 }
class product_supplierinfo_modified(osv.osv):
    _inherit='product.supplierinfo'
    _desciption="Synchronizing "
    
    def _get_order_lines(self,cr,uid,ids,name,args,context):
        res = {}
        for info in self.read(cr,uid,ids,['product_id','name'],context):
            list = []
            cr.execute('''
            select purchase_order_line.id from purchase_order_line 
            left join purchase_order on purchase_order_line.order_id = purchase_order.id where purchase_order_line.product_id = %s and purchase_order.partner_id = %s
            ''' %(info.get('product_id',False)[0],info.get('name',False)[0]))
            for order_line in cr.fetchall():
                list.append(order_line[0])
            res.update({info.get('id',False):list})
        return res
    
    _columns = {
                'service':fields.char('Service'),
                'supplier_price':fields.float('Supplier Price'),
                'date':fields.date('Latest Price Date'),
                'history_line':fields.function(_get_order_lines,method=True,type='many2many',relation="purchase.order.line",string="History")
                }
class purchase_order_line_modified(osv.osv):
    _inherit='purchase.order.line'
    _description='Purchase order Line'
    _columns={
#               'based_on':fields.char('Based On'),
              'lead_time':fields.char('Delivery Lead Time'),
              'refresh_prices':fields.boolean("Refresh Supplier Prices",help="If checked then the price lines in product supplier info will get overriden by this line  ")
              }

#Repeat Procurement Scheduler field set true
class procurement_order(osv.Model):
    _inherit = 'procurement.order'
    _description = "Setting scheduler field True"
    
    def _prepare_orderpoint_procurement(self, cr, uid, orderpoint, product_qty, context=None):
        return {'name': orderpoint.name,
                'date_planned': self._get_orderpoint_date_planned(cr, uid, orderpoint, datetime.today(), context=context),
                'product_id': orderpoint.product_id.id,
                'product_qty': product_qty,
                'company_id': orderpoint.company_id.id,
                'product_uom': orderpoint.product_uom.id,
                'location_id': orderpoint.location_id.id,
                'procure_method': 'make_to_order',
                'origin': orderpoint.name,
                'scheduler':True}
