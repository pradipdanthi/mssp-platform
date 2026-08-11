# Kevantic first-boot network wizard (interactive console / SSH login).
# Pink/magenta UI via kevantic-firstboot-netconfig. Completes once.
if [ -n "${PS1-}" ] && [ -z "${KEVANTIC_NETCONFIG_RAN-}" ]; then
  if [ ! -f /var/lib/kevantic/firstboot-network.done ] && [ -t 0 ] && [ -t 1 ]; then
    KEVANTIC_NETCONFIG_RAN=1
    export KEVANTIC_NETCONFIG_RAN
    if [ -x /usr/local/sbin/kevantic-firstboot-netconfig ]; then
      /usr/local/sbin/kevantic-firstboot-netconfig || true
    fi
  fi
fi
