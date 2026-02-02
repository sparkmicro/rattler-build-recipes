import os
import sys
import json
import hashlib
import subprocess
import urllib.request
from urllib.error import HTTPError


class AuthRemovingRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new_req = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new_req and req.host != new_req.host:
            if new_req.has_header("Authorization"):
                new_req.remove_header("Authorization")
        return new_req

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


def extract_package_info(filename):
    """Extract name, version, and build from conda filename."""
    # Format: name-version-build.conda or name-version-build.tar.bz2
    parts = filename.rsplit('-', 2)
    if len(parts) >= 3:
        name = parts[0]
        version = parts[1]
        build = parts[2].replace('.conda', '').replace('.tar.bz2', '')
        return name, version, build
    return None, None, None

def main():
    if len(sys.argv) < 4:
        print(
            "Usage: python upload_package.py <filepath> <channel> <token> [os] [--skip-hash-check]")
        sys.exit(1)

    filepath = sys.argv[1]
    channel = sys.argv[2]
    token = sys.argv[3]
    current_os = sys.argv[4] if len(
        sys.argv) > 4 and not sys.argv[4].startswith("--") else "Linux"
    skip_hash_check = "--skip-hash-check" in sys.argv
    
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
        req.add_header("User-Agent", "sparkmicro-rattler-build-upload/1.0")
        
        opener = urllib.request.build_opener(AuthRemovingRedirectHandler)
        with opener.open(req) as response:
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
        local_name, local_version, local_build = extract_package_info(filename)
        print(
            f"I: Package {local_name} v{local_version} (build {local_build}) exists on channel.")

        # Compare build strings to detect recipe changes
        # Build string is deterministic from recipe inputs, so if it matches, recipe is identical
        remote_build = remote_package.get("build")
        
        if local_build == remote_build:
            print(f"I: Build string matches ({local_build}). Recipe unchanged. Skipping upload.")
            return
        else:
            print(f"I: Build string differs (local: {local_build}, remote: {remote_build}). Recipe changed. Uploading.")
            should_upload = True
            force_upload = False
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
            
            # Check for specific failure case: "The package does not exist" on forced upload
            if result.returncode != 0 and force_upload and "The package does not exist" in result.stderr:
                print("W: Forced upload failed because package seems missing (ghost package). Retrying without --force.")
                if "--force" in cmd:
                    cmd.remove("--force")
                
                print(f"I: Retrying: {' '.join(cmd).replace(token, '***')}")
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
