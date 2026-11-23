#!/bin/bash
set -euo pipefail

readonly SERVICE_URL="${1:?usage: vod.sh <service url>}"
readonly PROFILE_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/kasual-desktop/vod-profile"
readonly WINDOW_NAME="kasual-vod"

mkdir -p "$PROFILE_DIR"

cat > "$PROFILE_DIR/user.js" <<'PREFS'
user_pref("media.eme.enabled", true);
user_pref("media.gmp-widevinecdm.enabled", true);
user_pref("media.gmp-widevinecdm.visible", true);
user_pref("media.autoplay.default", 0);
user_pref("full-screen-api.warning.timeout", 0);
user_pref("extensions.autoDisableScopes", 0);
user_pref("extensions.startupScanScopes", 15);
user_pref("browser.sessionstore.resume_from_crash", false);
user_pref("browser.shell.checkDefaultBrowser", false);
user_pref("browser.aboutwelcome.enabled", false);
user_pref("browser.startup.homepage_override.mstone", "ignore");
user_pref("startup.homepage_welcome_url", "");
user_pref("datareporting.policy.dataSubmissionPolicyBypassNotification", true);
user_pref("toolkit.telemetry.reportingpolicy.firstRun", false);
PREFS

exec firefox --no-remote --profile "$PROFILE_DIR" --name "$WINDOW_NAME" --kiosk "$SERVICE_URL"
