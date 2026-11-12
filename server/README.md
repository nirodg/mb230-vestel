# CIFS rig — run OpenTV's `aurora.elf` on the TV over the LAN

Temporary dev rig on your PC. The TV mounts a Samba share and runs our
`aurora.elf` from it via the stock `/conf/remote.txt` hook — so you iterate
the binary by re-copying one file, with **no further TV flash writes**.

## Confirmed launch chain (this firmware)
`/vendor/run.sh` (RUN_APPMGR=1) → `/conf/remote.txt` present →
`appmgr --applist=nvt.app.debug.ini` → `debug.ini` idtv program is
`run_aurora.sh` → it brings up eth0 (MAC `D4:E2:CC:EC:45:E9`), DHCP,
`insmod cifs.ko`, mounts `//<PC>/mb230cifs` at `/conf/remotelf`, and with
`isgdb=0` runs **`/conf/remotelf/aurora.elf`** directly = our binary.

## One-time PC setup
```
make -C stage1/launcher aurora.elf         # or the docker build (README there)
sudo server/setup_cifs.sh                  # installs samba, creates share+user
```
It prints the `remote.txt` line: `0:<PC-ip>:mb230:<password>`.
Requirements: TV + PC on the **same Ethernet LAN** (the hook uses eth0, not Wi-Fi).

## Arming (the one TV flash write — needs your go)
Because the service menu can't drop `remote.txt` and U-Boot can't write a
single file, `remote.txt` is placed by rewriting the whole `/conf` volume
once (current `/conf` + `remote.txt`), via the U-Boot `.scr` channel.
```
# make the RESTORE stick first (recovery net), verify you can read it back:
stage1/uboot/track_b_stick.sh restore --dump <dump_apdat0.bin> --stick /media/you/STICK
# then the WRITE stick:
stage1/uboot/track_b_stick.sh write --ip <PC> --user mb230 --pass <pw> \
    --dump <dump_apdat0.bin> --stick /media/you/STICK
```
Boot the TV **holding OK** to perform the write. On the next normal boot the
TV runs our `aurora.elf`: purple framebuffer + a log at `/conf/opentv_aurora.log`
(read it back with the dump probe).

## If anything looks wrong
Power-cycle + hold OK (U-Boot is untouched/signed) and run the **restore**
stick — `dump_apdat0.bin` is already on the write stick too. Worst case
without restoring is a `/conf` factory reset, not a brick. All writes stay
confined to `apdat0`; never add a write to any boot/signed partition.

## Security / hygiene
LAN-only share (`hosts allow` is set), a dedicated nologin user, read-only
export. Tear it down when done: remove the `[mb230cifs]` block from
`/etc/samba/smb.conf`, `smbpasswd -x mb230`, `rm -rf /srv/mb230cifs`.
Don't expose it to the internet.
