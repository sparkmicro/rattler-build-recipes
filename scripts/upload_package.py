import os
import sys
import json
import hashlib
import subprocess
import urllib.request
from urllib.error import HTTPError

def calculate_sha256(filepath):
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def get_subdir(filepath):
    # rattler-build output is usually output/<subdir>/<package.conda>
    # We can try to infer from path
    parts = os.path.normpath(filepath).split(os.sep)
    if len(parts) > 1:
        return parts[-2]
    return "linux-64" # fallback, should not happen in CI structure

def main():
    if len(sys.argv) < 4:
        print("Usage: python upload_package.py <filepath> <channel> <token>")
        sys.exit(1)

    filepath = sys.argv[1]
    channel = sys.argv[2]
    token = sys.argv[3]
    current_os = sys.argv[4] if len(sys.argv) > 4 else "Linux"
    
    filename = os.path.basename(filepath)
    subdir = get_subdir(filepath)
    
    if subdir == "noarch" and current_os != "Linux":
        print(f"I: Skipping noarch package {filename} on {current_os} to avoid race condition.")
        return
    
    print(f"I: Processing {filepath} (subdir: {subdir})")

    # Fetch repodata
    repodata_url = f"https://prefix.dev/{channel}/{subdir}/repodata.json"
    print(f"I: Fetching repodata from {repodata_url}")
    
    try:
        req = urllib.request.Request(repodata_url)
        # Use simple Bearer auth. Note: prefix.dev might expect just the token or Bearer
        # Based on curl test, it used "Bearer <token>"
        req.add_header("Authorization", f"Bearer {token}")
        
        with urllib.request.urlopen(req) as response:
            repodata = json.loads(response.read().decode())
    except HTTPError as e:
        print(f"W: Failed to fetch repodata (HTTP {e.code}). Assuming new package.")
        repodata = {}
    except Exception as e:
        print(f"W: Error fetching repodata: {e}. Assuming new package.")
        repodata = {}

    packages = repodata.get("packages.conda", {})
    
    remote_package = packages.get(filename)
    
    should_upload = False
    force_upload = False
    
    if remote_package:
        print(f"I: Package {filename} exists on channel.")
        remote_sha = remote_package.get("sha256")
        local_sha = calculate_sha256(filepath)
        
        print(f"I: Local SHA: {local_sha}")
        print(f"I: Remote SHA: {remote_sha}")
        
        if local_sha == remote_sha:
            print("I: content matches. Skipping upload.")
            return
        else:
            print("I: Content differs. Forcing upload.")
            should_upload = True
            force_upload = True
    else:
        print(f"I: Package {filename} not found on channel. Uploading.")
        should_upload = True
        force_upload = False
        
    if should_upload:
        cmd = [
            "pixi", "run", "rattler-build", "upload", "prefix",
            "--channel", channel,
            "--api-key", token,
            filepath
        ]
        if force_upload:
            cmd.insert(5, "--force")
            
        print(f"I: Running: {' '.join(cmd).replace(token, '***')}")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)
            if result.returncode != 0:
                print(f"E: Upload failed with return code {result.returncode}")
                sys.exit(result.returncode)
        except Exception as e:
            print(f"E: Failed to execute upload command: {e}")
            sys.exit(1)
    
if __name__ == "__main__":
    main()
