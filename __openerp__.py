# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2004-2010 Tiny SPRL (<http://tiny.be>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#############################################################################
{
    'name' : 'Captherm Customizations',
    'version' : '1.1',
    'author' : 'Shivam Goyal',
    'category' : 'Customizations',
    'description' : """
Captherm Customizations
    """,
    'website': 'www.captherm.com',
    'images' : [],
    'depends' : ['base','product','purchase','sale','stock','account','account_accountant','mrp',],
    
    'data': ['res_user_data.xml',
             'product_custom_view.xml',
             'purchase_custom.xml','sale_custom.xml',
             'res_users_view.xml',
             'mrp_bom_sequence.xml',
             'security/ir.model.access.csv',
             'mrp_view.xml'
            ],
    
    'demo': [],
    
    'test': [],
    'installable': True,
    'auto_install': False,
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
