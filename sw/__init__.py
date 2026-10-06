"""StockWaakhond V7.1 - gedeelde kern van de bevroren forward-test.

Deze map bevat de rekenkern zonder enige schermcode. Zo kan dezelfde
berekening getest worden, lokaal gedraaid worden en online getoond worden,
zonder dat er drie varianten van dezelfde formule ontstaan.
"""

__all__ = [
    "beurskalender",   # wanneer is een koers definitief
    "strategy",        # de bevroren scoreformule
    "ledger",          # het append-only logboek
    "portfolio",       # de virtuele portefeuille
    "prices",          # koersen ophalen bij Yahoo
    "supabase_io",     # praten met de database
]
