#!/usr/bin/env bash
# Stand up the `mb230cifs` Samba share that the TV mounts to run our
# aurora.elf (via the /conf/remote.txt hook). LAN-only, temporary dev rig.
# Run on your PC (needs sudo). Does NOT touch the TV.
#
#   sudo server/setup_cifs.sh [--elf stage1/launcher/aurora.elf] [--user mb230]
#
# Prints the remote.txt line to feed to stage1/uboot/track_b_stick.sh.
set -euo pipefail
ELF="stage1/launcher/aurora.elf"; USER_NAME="mb230"; SHARE="/srv/mb230cifs"
while [ $# -gt 0 ]; do case "$1" in
  --elf) ELF="$2"; shift 2;; --user) USER_NAME="$2"; shift 2;;
  --share) SHARE="$2"; shift 2;; *) echo "unknown arg: $1"; exit 1;; esac; done

[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }
[ -f "$ELF" ] || { echo "aurora.elf not found at $ELF (build it first: make -C stage1/launcher ... or see README)"; exit 1; }

echo "[*] installing samba (if needed) ..."
if ! command -v smbd >/dev/null; then
  (apt-get update -qq && apt-get install -y -qq samba) || { echo "install samba manually"; exit 1; }
fi

echo "[*] creating share dir $SHARE and copying aurora.elf ..."
mkdir -p "$SHARE"
install -m 0755 "$ELF" "$SHARE/aurora.elf"
chmod 0755 "$SHARE"

echo "[*] creating samba user '$USER_NAME' ..."
id "$USER_NAME" >/dev/null 2>&1 || useradd -M -s /usr/sbin/nologin "$USER_NAME"
echo "    set this user's Samba password (you'll put it in remote.txt):"
smbpasswd -a "$USER_NAME"

echo "[*] installing share config ..."
CONF=/etc/samba/smb.conf
if ! grep -q '^\[mb230cifs\]' "$CONF" 2>/dev/null; then
  { echo; cat "$(dirname "$0")/smb-mb230cifs.conf"; } >> "$CONF"
else
  echo "    [mb230cifs] already present in $CONF — leaving as is"
fi
sed -i "s#path = /srv/mb230cifs#path = $SHARE#; s#valid users = mb230#valid users = $USER_NAME#" "$CONF" || true

echo "[*] testbed config:"; testparm -s 2>/dev/null | sed -n '/\[mb230cifs\]/,/^$/p' || true
echo "[*] restarting smbd ..."; systemctl restart smbd 2>/dev/null || service smbd restart || true

IP=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{print $7; exit}')
echo
echo "================= CIFS rig ready ================="
echo "  share:   //${IP:-<this-PC-ip>}/mb230cifs  ->  $SHARE (serves aurora.elf)"
echo "  user:    $USER_NAME   (password you just set)"
echo
echo "  Put this in the TV's /conf/remote.txt (isgdb=0 => run directly):"
echo "      0:${IP:-<this-PC-ip>}:$USER_NAME:<the-password>"
echo
echo "  Then (at go-time):"
echo "      stage1/uboot/track_b_stick.sh write --ip ${IP:-<ip>} --user $USER_NAME --pass <pw> \\"
echo "          --dump <dump_apdat0.bin> --stick /media/you/STICK"
echo "  Update aurora.elf later by re-copying it into $SHARE — no TV write."
echo "=================================================="
