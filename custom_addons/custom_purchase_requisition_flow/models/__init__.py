# -*- coding: utf-8 -*-

# CORREGIDO: Importar modelos base antes de los que dependen de ellos
from . import purchase_requisition # Importar primero
from . import account_move         # Importar segundo
from . import purchase_requisition_line # Importar al final
