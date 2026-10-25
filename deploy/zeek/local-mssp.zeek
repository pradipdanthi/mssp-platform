## MSSP site policy for the Zeek Docker sensor (extra notices for SOC).
## Pair with deploy/wazuh-manager/mssp_zeek_rules.xml (level >=10 pages).

@load protocols/ssh/detect-bruteforcing
@load protocols/ssl/validate-certs
@load frameworks/software/vulnerable
@load frameworks/software/version-changes

redef LogAscii::use_json = T;

# SSH brute-force notices (Scan::* requires optional bro-simple-scan package).
redef SSH::password_guesses_limit = 3;
