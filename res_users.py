from openerp.osv import fields, osv
import time

class users_position(osv.Model):
    _name="users.position"
    _description = "Making Organizational Positions"
    _columns = {
                'name':fields.char('Organizational Position')
                }
    
class res_users(osv.Model):
    _inherit = "res.users"
    _description = "Adding Position field"
    
 
    _columns = {
                'positions':fields.many2one('users.position',"Position",
                                              track_visibility = True
                                             ),

                }

