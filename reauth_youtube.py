#!/usr/bin/env python3
"""
One-time re-authorization for the DevOps Genius Zone bot.

Why: the GOOGLE_CREDENTIALS secret was created before the
youtube.force-ssl scope was added, so caption uploads fail with
403 "insufficient authentication scopes". An old refresh token can't be
given new scopes - Google needs one fresh "Allow". This prints a NEW
value for the GOOGLE_CREDENTIALS secret.

Run on your own computer (it opens a browser):
    pip install google-auth-oauthlib
    python reauth_youtube.py                 # auto-finds the file
    python reauth_youtube.py <path-to-file>  # or point at it

It accepts EITHER of these files:
  1) The OAuth client file from Google Cloud Console
     (APIs & Services -> Credentials -> your OAuth 2.0 Client -> Download JSON).
     Google names it like client_secret_XXXX.apps.googleusercontent.com.json
  2) An old token.json / the old GOOGLE_CREDENTIALS JSON (it contains
     client_id and client_secret, which is all this script needs).

Sign in with the Google account that OWNS the DevOps Genius Zone channel,
pick that channel if asked, and tick every permission. Then paste the
printed JSON into GitHub -> repo Settings -> Secrets and variables ->
Actions -> GOOGLE_CREDENTIALS -> Update.
"""
import glob
import json
import os
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",  # captions
]


def find_file():
    if len(sys.argv) > 1:
        return sys.argv[1]
    here = os.path.dirname(os.path.abspath(__file__))
    patterns = ["client_secret*.json", "credentials.json", "token.json", "google_credentials*.json"]
    for folder in (os.getcwd(), here):
        for pat in patterns:
            hits = sorted(glob.glob(os.path.join(folder, pat)))
            if hits:
                return hits[0]
    return None


def client_config_from(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    # Case 1: Google Cloud Console download -> {"installed": {...}} or {"web": {...}}
    if "installed" in data:
        return data, "desktop"
    if "web" in data:
        return {"installed": data["web"]}, "web"
    # Case 2: an authorized-user token (old token.json / GOOGLE_CREDENTIALS)
    if data.get("client_id") and data.get("client_secret"):
        return {
            "installed": {
                "client_id": data["client_id"],
                "client_secret": data["client_secret"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": data.get("token_uri", "https://oauth2.googleapis.com/token"),
                "redirect_uris": ["http://localhost"],
            }
        }, "token"
    raise SystemExit(f"{path} has no client_id/client_secret - not an OAuth client or token file.")


def main():
    path = find_file()
    if not path or not os.path.exists(path):
        raise SystemExit(
            "No OAuth client file found.\n"
            "Put ONE of these next to this script and run again:\n"
            "  - client_secret_....json  (Google Cloud Console -> APIs & Services -> Credentials ->\n"
            "    your OAuth 2.0 Client ID -> Download JSON)\n"
            "  - your old token.json (has client_id + client_secret)\n"
            "Or pass the path:  python reauth_youtube.py C:\\path\\to\\file.json"
        )
    config, kind = client_config_from(path)
    print(f"Using {os.path.basename(path)} ({kind} client).")
    if kind == "web":
        print("NOTE: this is a 'Web application' client. If Google shows redirect_uri_mismatch,\n"
              "      add http://localhost:8080/ to its Authorized redirect URIs in Cloud Console\n"
              "      (or create a 'Desktop app' client), then run again.")

    flow = InstalledAppFlow.from_client_config(config, SCOPES)
    # Fixed port so a Web client only needs one redirect URI registered.
    # prompt=consent forces a NEW refresh token that carries the new scope.
    creds = flow.run_local_server(port=8080, prompt="consent", access_type="offline")

    granted = set(creds.granted_scopes or creds.scopes or [])
    missing = [s for s in SCOPES if s not in granted]
    if missing:
        print(f"WARNING: not granted (tick all boxes on the consent screen and retry): {missing}")
    if not creds.refresh_token:
        print("WARNING: no refresh_token returned - remove the app at "
              "https://myaccount.google.com/permissions and run again.")

    out = json.loads(creds.to_json())
    with open("GOOGLE_CREDENTIALS_new.json", "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))
    print("\n=== Paste everything below into the GOOGLE_CREDENTIALS secret ===\n")
    print(json.dumps(out, separators=(",", ":")))
    print("\n(Also saved to GOOGLE_CREDENTIALS_new.json - delete it after updating the secret.)")


if __name__ == "__main__":
    main()
