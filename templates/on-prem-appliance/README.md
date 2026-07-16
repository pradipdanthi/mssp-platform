# MSSP On-Prem Appliance Template

This bundle is a safe starting template. Replace every angle-bracket placeholder
before deployment. Never commit activation tokens or appliance API keys.

1. Ask a platform administrator for a one-time activation token.
2. Copy `docker-compose.yml.template` to `docker-compose.yml` on the appliance.
3. Replace `<APPLIANCE_IMAGE>`, `<CONTROL_PLANE_URL>`, `<ACTIVATION_TOKEN>`,
   `<APPLIANCE_NAME>`, and `<AGENT_VERSION>`.
4. Start the appliance and confirm registration in the admin Appliances page.
5. Store the returned durable appliance API key in a local secret store; do not
   place it in Git or send it to the customer portal.

The appliance sends normalized metadata only. Raw events, IP addresses,
credentials, packet captures, and internal notes must stay local.
