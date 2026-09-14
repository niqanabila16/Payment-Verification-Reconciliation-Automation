# Sample Teller Strings

Format: `<branch_code>/<sender_name>/<entity_name>/<entity_type>/<bank_code>/RM<amount>/<reference_number>/<status_code>`

See Technical Design Document Section 11 for the full field definitions and how to sanitize "/" characters inside names.

## Valid Examples

KJG/MOHD IKHWAN BIN MOBIN/IKMO NIAGA/COMPANY/RHB/RM708.50/1055889/CHK

KJG/JUNAEDI NURJANNAH/-/INDIVIDUAL/RHB/RM300.00/-/CHK

PJY/SITI AMINAH BINTI HASSAN/-/INDIVIDUAL/MAYBANK/RM1200.00/IBG20260902551/CHK

PJY/RAJESH A-L KUMAR/-/INDIVIDUAL/MAYBANK/RM450.75/DNT20260905332/CHK

## Example Requiring Sanitization (name contains "/")

Raw OCR input   : RAJESH A/L KUMAR
After sanitization: RAJESH A-L KUMAR   (see Technical Design Document Section 11.3)

## Example With a Missing Field (no reference available from the QR channel)

KJG/DINI/-/INDIVIDUAL/RHB/RM2050.00/-/CHK

> Empty fields are filled with a "-" placeholder, not simply left blank -- see Technical Design Document Section 11.4. A transaction without a reference automatically drops to Level 3/4 matching (see Section 15.3).
