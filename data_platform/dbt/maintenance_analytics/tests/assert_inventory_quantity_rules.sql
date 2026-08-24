select movement_id
from {{ ref('fact_inventory_movement') }}
where quantity <= 0
   or resulting_on_hand_quantity < 0
   or resulting_reserved_quantity < 0
   or resulting_reserved_quantity > resulting_on_hand_quantity
   or (
       movement_type in ('issue', 'transfer_out', 'adjustment_decrease', 'damaged_scrapped')
       and signed_quantity >= 0
   )
   or (
       movement_type in ('opening_balance', 'receipt', 'return', 'transfer_in', 'adjustment_increase')
       and signed_quantity <= 0
   )
