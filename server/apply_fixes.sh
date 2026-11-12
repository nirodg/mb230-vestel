#!/usr/bin/env bash
# Apply the Samba-side fixes for the TV connection (run on the PC, sudo).
#   - refresh aurora.elf in the share (the no-exit build)
#   - enable SMB1/NTLMv1 so the TV's kernel-4.9 cifs.ko can mount
#   - raise log level so ANY TV contact is captured
# Idempotent. Does NOT touch the TV.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
ELF="$REPO/stage1/launcher/aurora.elf"
SHARE="/srv/mb230cifs"; CONF=/etc/samba/smb.conf
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }
[ -f "$ELF" ] || { echo "build aurora.elf first"; exit 1; }

echo "[*] refresh share binary"; install -m 0755 "$ELF" "$SHARE/aurora.elf"

echo "[*] enable SMB1/NTLMv1 + verbose logging in [global]"
# insert into the [global] section if not already present
if ! grep -q 'server min protocol = NT1' "$CONF"; then
  awk '
    /^\[global\]/ && !done {
      print;
      print "   server min protocol = NT1";
      print "   server max protocol = SMB3";
      print "   ntlm auth = yes";
      print "   lanman auth = no";
      print "   client min protocol = NT1";
      print "   log level = 3";
      print "   log file = /var/log/samba/log.%m";
      done=1; next
    }
    { print }
  ' "$CONF" > "$CONF.new" && mv "$CONF.new" "$CONF"
else
  echo "    already present"
fi

echo "[*] testparm check"; testparm -s 2>/dev/null | grep -iE 'min protocol|ntlm auth|log level' || true
echo "[*] restart smbd"; systemctl restart smbd 2>/dev/null || service smbd restart || true
echo "[*] clear old client logs so the next TV attempt is obvious"
rm -f /var/log/samba/log.192.168.* 2>/dev/null || true
IP=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{print $7; exit}')
echo
echo "[ok] Samba ready at //${IP:-<PC>}/mb230cifs (SMB1 enabled, verbose logs)."
echo "     After a TV boot, check: sudo tail -n 50 /var/log/samba/log.192.168.* 2>/dev/null"
