# P.act Lidar edge v1.0.1-lidar

This is the Pro edge **v1.0.1** package with **ONVIF v1.1.0 (a8e37f1f)**, patched for the P.act Lidar. The Lidar has a Livox Avia lidar and a zoom camera, but no wide camera. It runs Debian 13 trixie, and its user is `poe`.

The edge package itself is not part of this repository. `build_lidar_pkg.py` takes the Pro v1.0.1 package and patches it into a bundle. The bundle zip is internal and not published here.

## Install on a device (account poe)

Run these on the Lidar:

    # On the PC: scp edge_v1.0.1-lidar.zip poe@<IP>:~/
    cd ~ && python3 -m zipfile -e edge_v1.0.1-lidar.zip . && cd edge_v1.0.1-lidar
    bash install_lidar.sh          # enter the sudo password once
    sudo reboot

- The installer reads the zoom camera account from the vendor script `~/cm5-setup/run_zoomcamera.sh`. To set it yourself, pass `ZOOM_USER=..` and `ZOOM_PASS=..`.
- Pass the TURN value as `TURN_PASSWORD=..`. Without it, remote video may not work from outside the same network.
- Running the installer again upgrades the device. It keeps settings.json, mediamtx.yml and the device ID.

From a PC, install everything in one go: `python deploy_bundle.py <IP> --zip build/edge_v1.0.1-lidar.zip`. The first install also takes the rollback snapshot.

## Differences from Pro v1.0.1

| | Pro | Lidar |
|---|---|---|
| Account / path | ptz, /home/ptz | **poe, /home/poe** |
| Model marker | - | `/etc/pact-model` = lidar |
| Main video (my_camera) | Wide camera (rpiCamera) | **Zoom camera RTSP** (192.168.1.68/stream1) |
| Wide camera and AI (Hailo, wide-watchdog, models) | Installed | **Skipped.** Requests to turn AI on are refused |
| Sensor LAN | eth1 fixed at 192.168.1.10, adapter name pinned | **Skipped.** The vendor's br-sensor bridge (eth1+eth2) is left as is |
| Kiosk (HDMI lock) | Installed | Skipped by default. `KIOSK=1` installs it |
| Python packages | pip | **apt** (Debian 13 blocks pip) |
| selfcheck | Checks eth1 and Hailo | Checks br-sensor; skips Hailo |
| Wide camera settings (rpiCamera*) | Applied to my_camera | **Not applied.** On the Lidar, flipping the mount mode or saving or resetting settings would otherwise close and reopen the zoom video and cut the recording. The zoom camera's own flip still works |

The edge files are patched as follows:
- `/home/ptz` becomes `/home/poe`.
- The services run as poe (edge-whep-bridge, updater, platform_mqtt group).
- In the mediamtx template, my_camera becomes the zoom camera RTSP stream.
- In settings_handler, rpiCamera restore and AI start are disabled, and `_mtx_patch_path` drops wide-camera values.
- In selfcheck, the checks follow the Lidar layout.

## Notes

- **Platform remote updates** use the Pro install.sh. On a Lidar, that installer stops at the start because the user ptz does not exist, so nothing on the device changes. Update a Lidar with this bundle instead.
- **Mount mode** (stand or hang, set from the web UI or the platform) flips the sign of the ONVIF tilt. In hang mode, tilt values are negative (0 to −1.48).
- **The tilt firmware range differs per unit** (for example 0 to 1.48, or 0.05 to 1.49). ONVIF uses the range it reads from the motor board.
- **External RTSP** works as on the Pro: it needs admin and the video password. Connections from inside the device are allowed.
- **ONVIF account check:** onvif_srvd v1.1.0 only reads the web password hash from `/home/ptz/edge/.device_auth`. On the Lidar the file is in `/home/poe/edge`, so the installer adds a link at `/home/ptz/edge/.device_auth`; the rollback removes it.
  - Without this link, ODM and NVRs can log in only with the initial password (the serial) even after the web password is changed.
  - The video (RTSP) then returns 401. After 5 failures, that PC's IP is locked for 60 seconds, so the web preview from the same PC is blocked too.
  - This was fixed on 2026-11-16, and the onvif source will read both paths in a later release.

## Roll back to the vendor shipping state

On the PC, run `python rollback.py <IP>`. It compares the device with the pre-install snapshot and removes only what edge added: services, files, apt packages and pip packages. Then it reboots the device.

## Tests (`test/`)

| File | What it does |
|---|---|
| `lidar_test.py <IP>` | Shipping test before install. Covers the test guide items (info, lidar, zoom video, zoom control, pan/tilt), plus end-stop heat and wobble from Q, then moves to 0,0 |
| `lidar_edge_test.py <IP>` | Test after install. Covers services and versions, br-sensor, lidar, my_camera and detection_zoom video, selfcheck, the ONVIF function test, then 0,0 via ONVIF |
| `motor_check_dev.py` | Runs on the device. Only V/I/E/Q/S/T, no commands that change settings |
| `onvif_function_test.py` | Runs on the device. Covers move status, continuous move, presets with Korean names, end-to-end heat over 3 round trips, and GetStatus Error |

Accounts come from the `LIDAR_USER` and `LIDAR_PASS` environment variables. Results go to `./data/` (`LIDAR_DATA`), which is not committed. If you change the web password and set `LIDAR_WEB_PASS`, `lidar_edge_test.py` also checks the ONVIF login (admin + web password) and external RTSP with authentication.

## Verified (2026-11-16)

<lidar-unit> (Debian 13, motor FW v2.5.1): first install, then an upgrade from the bundle, then a reboot. Services 9/9, lidar O, zoom video O, ONVIF 5/5, selfcheck fail 0, 0,0 O.
