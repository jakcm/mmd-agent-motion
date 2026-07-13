#!/usr/bin/env python3
"""
CDP-based arm jump test for mmd-agent-motion.
Loads the test page, executes the MPL nod command, monitors arm bone quaternions.
"""
import json, subprocess, time, sys, os, signal
import websocket

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PROJECT_DIR = "/Users/admin/projects/mmd-agent-motion"
PORT = 8791

# The MPL to test (exact user input)
MPL_CODE = "@pose nod{head bend forward 30;neck bend forward 10;}@animation nod_anim{0.2:nod;}main{nod_anim;}"

def start_chrome():
    proc = subprocess.Popen([
        CHROME,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--remote-debugging-port=0",  # random port
        "--user-data-dir=/tmp/chrome-arm-jump-test",
        "--disable-features=IsolateOrigins,site-per-process",
        "--enable-unsafe-swiftshader",
        "--dump-dom",
        f"http://127.0.0.1:{PORT}/test_arm_jump.html",
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return proc

def start_server():
    proc = subprocess.Popen(
        ["python3", "-m", "http.server", str(PORT)],
        cwd=PROJECT_DIR,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    time.sleep(1)
    return proc

def cdp(ws, method, params=None, timeout=30):
    global msg_id
    msg_id += 1
    msg = {"id": msg_id, "method": method}
    if params:
        msg["params"] = params
    ws.send(json.dumps(msg))
    deadline = time.time() + timeout
    while time.time() < deadline:
        ws.settimeout(timeout)
        try:
            resp = json.loads(ws.recv())
            if resp.get("id") == msg_id:
                return resp
            # events get printed
            if "method" in resp:
                handle_event(resp)
        except websocket.WebSocketTimeoutException:
            break
    return None

def handle_event(event):
    method = event.get("method", "")
    if method == "Runtime.consoleAPICalled":
        args = event.get("params", {}).get("args", [])
        text = " ".join(a.get("value", a.get("description", "")) for a in args)
        if "[TEST]" in text or "[MPL]" in text or "jump" in text.lower() or "arm" in text.lower():
            print(f"  CONSOLE: {text}")
    elif method == "Runtime.exceptionThrown":
        exc = event.get("params", {}).get("exceptionDetails", {})
        print(f"  EXCEPTION: {exc.get('text', '')} - {exc.get('exception', {}).get('description', '')}")

msg_id = 0

def main():
    print("=== MPL Arm Jump Test ===")
    print(f"MPL: {MPL_CODE}")
    print()
    
    # Start HTTP server
    print("[1] Starting HTTP server...")
    server = start_server()
    
    # Start Chrome
    print("[2] Starting headless Chrome...")
    chrome = start_chrome()
    time.sleep(3)
    
    # Find the debug port from stderr
    stderr_out = chrome.stderr.read1(4096).decode(errors='replace') if hasattr(chrome.stderr, 'read1') else ""
    # Try to get websocket URL
    import urllib.request
    ws_url = None
    for attempt in range(10):
        try:
            resp = urllib.request.urlopen("http://127.0.0.1:0/json" if "DevTools" not in stderr_out else "http://127.0.0.1:0/json")
            break
        except:
            pass
    
    # Actually let's try a different approach - read the debug port from the output
    # Chrome prints: "DevTools listening on ws://127.0.0.1:PORT/devtools/browser/..."
    time.sleep(2)
    
    # Get port from /json endpoint - we need to find the actual port
    # Let's read from stderr of chrome process
    import threading
    stderr_lines = []
    def read_stderr():
        while True:
            line = chrome.stderr.readline()
            if not line:
                break
            stderr_lines.append(line.decode(errors='replace'))
    
    # Restart Chrome with captured stderr
    chrome.kill()
    chrome.wait()
    
    print("[2b] Restarting Chrome with stderr capture...")
    chrome_proc = subprocess.Popen([
        CHROME,
        "--headless=new",
        "--disable-gpu", 
        "--no-sandbox",
        "--remote-debugging-port=0",
        f"--user-data-dir=/tmp/chrome-arm-jump-test-{os.getpid()}",
        "--disable-features=IsolateOrigins,site-per-process",
        "--enable-unsafe-swiftshader",
        f"http://127.0.0.1:{PORT}/test_arm_jump.html",
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    time.sleep(3)
    
    # Read stderr to find DevTools port
    import select
    stderr_data = b""
    while select.select([chrome_proc.stderr], [], [], 2.0)[0]:
        chunk = chrome_proc.stderr.read1(4096) if hasattr(chrome_proc.stderr, 'read1') else chrome_proc.stderr.read(4096)
        if not chunk:
            break
        stderr_data += chunk
    
    stderr_text = stderr_data.decode(errors='replace')
    print(f"  Chrome stderr: {stderr_text[:500]}")
    
    # Extract ws:// URL
    import re
    ws_match = re.search(r'(ws://127\.0\.0\.1:\d+/devtools/browser/[^\s]+)', stderr_text)
    if not ws_match:
        print("ERROR: Could not find DevTools WebSocket URL")
        chrome_proc.kill()
        server.kill()
        sys.exit(1)
    
    ws_url = ws_match.group(1)
    print(f"  DevTools: {ws_url}")
    
    # Connect to Chrome DevTools
    print("[3] Connecting to DevTools...")
    ws = websocket.create_connection(ws_url, timeout=10)
    
    # Enable Runtime
    cdp(ws, "Runtime.enable")
    
    # Wait for page to be ready
    print("[4] Waiting for test page to load (models + WASM)...")
    
    # Poll until __test.status == 'ready' or 'test complete'
    for i in range(120):  # up to 2 minutes
        resp = cdp(ws, "Runtime.evaluate", {
            "expression": "JSON.stringify(window.__test ? {status: window.__test.status, bones: Object.keys(window.__test.bones).length} : {status: 'no __test yet'})",
            "returnByValue": True
        })
        val = resp.get("result", {}).get("result", {}).get("value", "")
        if val:
            data = json.loads(val) if val.startswith('{') else {"status": val}
            status = data.get("status", "")
            print(f"  [{i}] Status: {status}")
            if status == "ready":
                break
            if status == "test complete":
                break
        time.sleep(2)
    else:
        print("ERROR: Page did not reach 'ready' state in time")
        ws.close()
        chrome_proc.kill()
        server.kill()
        sys.exit(1)
    
    # Get initial bone state
    print("\n[5] Capturing initial bone state...")
    resp = cdp(ws, "Runtime.evaluate", {
        "expression": "JSON.stringify(window.__test.bones)",
        "returnByValue": True
    })
    initial_bones = json.loads(resp.get("result", {}).get("result", {}).get("value", "{}"))
    print("  Initial arm bones:")
    for name in ['右腕', '左腕', '右肩', '左肩', '右ひじ', '左ひじ', '右手首', '左手首', '頭', '首']:
        if name in initial_bones:
            print(f"    {name}: {initial_bones[name]}")
    
    # Also check what the MPL compiler outputs for this code
    print("\n[6] Checking MPL compilation - track analysis...")
    resp = cdp(ws, "Runtime.evaluate", {
        "expression": """
        (function() {
            const mplCode = """ + json.dumps(MPL_CODE) + """;
            const normalized = mplCode
                .replace(/\\{/g, ' {\\n').replace(/\\}/g, '\\n}\\n')
                .replace(/;/g, ';\\n').replace(/\\n\\s*\\n/g, '\\n').trim();
            
            // Check what sanitizeMPL does (if available)
            let sanitized = normalized;
            if (typeof sanitizeMPL === 'function') {
                sanitized = sanitizeMPL(normalized);
            }
            
            // Check involved bones extraction
            const involvedBones = new Set(
                (sanitized.match(/^(\\s*)(\\w+)\\s+(bend|turn|sway|move|reset)/gm) || [])
                    .map(line => line.trim().split(/\\s+/)[0])
            );
            
            return JSON.stringify({
                normalized: normalized,
                sanitized: sanitized,
                involvedBones: [...involvedBones]
            });
        })()
        """,
        "returnByValue": True
    })
    mpl_info = json.loads(resp.get("result", {}).get("result", {}).get("value", "{}"))
    print(f"  Normalized MPL:\n{mpl_info.get('normalized', '?')}")
    print(f"  Sanitized MPL:\n{mpl_info.get('sanitized', '?')}")
    print(f"  Involved bones (English): {mpl_info.get('involvedBones', [])}")
    
    # Now compile and check tracks
    print("\n[7] Compiling MPL and checking VMD tracks...")
    resp = cdp(ws, "Runtime.evaluate", {
        "expression": """
        (async function() {
            const mplCode = """ + json.dumps(MPL_CODE) + """;
            const normalized = mplCode
                .replace(/\\{/g, ' {\\n').replace(/\\}/g, '\\n}\\n')
                .replace(/;/g, ';\\n').replace(/\\n\\s*\\n/g, '\\n').trim();
            let sanitized = normalized;
            if (typeof sanitizeMPL === 'function') {
                sanitized = sanitizeMPL(normalized);
            }
            
            const vmdBytes = mplCompiler.compile(sanitized);
            const blob = new Blob([vmdBytes], { type: 'application/octet-stream' });
            const url = URL.createObjectURL(blob);
            
            return new Promise((resolve) => {
                const loader = new THREE.MMDLoader();
                loader.loadAnimation(url, window.__test.mesh, (anim) => {
                    URL.revokeObjectURL(url);
                    
                    const trackInfo = anim.tracks.map(t => {
                        const m = t.name.match(/bones\\[(.+?)\\]/);
                        return { bone: m ? m[1] : t.name, times: Array.from(t.times), values: Array.from(t.values).map(v => +v.toFixed(4)) };
                    });
                    
                    resolve(JSON.stringify({
                        duration: anim.duration,
                        trackCount: anim.tracks.length,
                        tracks: trackInfo,
                        allBoneNames: trackInfo.map(t => t.bone)
                    }));
                }, undefined, (err) => {
                    resolve(JSON.stringify({error: String(err)}));
                });
            });
        })()
        """,
        "returnByValue": True,
        "awaitPromise": True
    })
    track_data_str = resp.get("result", {}).get("result", {}).get("value", "{}")
    track_data = json.loads(track_data_str)
    
    if "error" in track_data:
        print(f"  ERROR: {track_data['error']}")
    else:
        print(f"  VMD duration: {track_data.get('duration', '?')}s")
        print(f"  Total tracks: {track_data.get('trackCount', '?')}")
        print(f"  All bone names in VMD: {track_data.get('allBoneNames', [])}")
        
        # Check if arm bones are in the VMD
        arm_bones_in_vmd = [b for b in track_data.get('allBoneNames', []) 
                           if any(arm in b for arm in ['腕', '肩', 'ひじ', '手首', 'arm', 'shoulder', 'elbow', 'wrist'])]
        head_neck_bones = [b for b in track_data.get('allBoneNames', [])
                          if any(kw in b for kw in ['頭', '首', 'head', 'neck'])]
        
        print(f"\n  Head/neck tracks: {head_neck_bones}")
        print(f"  Arm-related tracks: {arm_bones_in_vmd}")
        
        if arm_bones_in_vmd:
            print(f"\n  ⚠️  WARNING: VMD contains arm bone tracks! These may cause jumping!")
            print(f"  Arm tracks detail:")
            for track in track_data.get('tracks', []):
                if track['bone'] in arm_bones_in_vmd:
                    print(f"    {track['bone']}: times={track['times'][:5]}... values(first10)={track['values'][:10]}...")
        else:
            print(f"\n  ✅ VMD does NOT contain arm bone tracks - good!")
        
        # Print all track details for analysis
        print(f"\n  All track details:")
        for track in track_data.get('tracks', []):
            print(f"    {track['bone']}: {len(track['times'])} keyframes")
            print(f"      times: {track['times'][:8]}")
            print(f"      values (first 12): {track['values'][:12]}")
    
    # Now execute the MPL and watch for jumps
    print("\n[8] Executing MPL and monitoring arm bone quaternions...")
    
    # Reset jumps
    cdp(ws, "Runtime.evaluate", {"expression": "window.__test.jumps = []"})
    
    # Execute the MPL
    resp = cdp(ws, "Runtime.evaluate", {
        "expression": """
        (async function() {
            const result = await window.__test.executeMPL(""" + json.dumps(MPL_CODE) + """);
            return JSON.stringify(result);
        })()
        """,
        "returnByValue": True,
        "awaitPromise": True
    }, timeout=60)
    
    result_str = resp.get("result", {}).get("result", {}).get("value", "{}")
    result = json.loads(result_str)
    
    print("\n  === RESULTS ===")
    print("  Bone diffs after MPL execution:")
    for bone, diff in result.get("diffs", {}).items():
        is_arm = bone in ['右腕', '左腕', '右肩', '左肩', '右ひじ', '左ひじ', '右手首', '左手首']
        marker = "🔴" if (is_arm and diff > 0.01) else ("🟢" if is_arm else "  ")
        label = " [ARM]" if is_arm else ""
        print(f"    {marker} {bone}{label}: {diff}")
    
    # Get frame-level jumps
    resp = cdp(ws, "Runtime.evaluate", {
        "expression": "JSON.stringify(window.__test.jumps)",
        "returnByValue": True
    })
    jumps = json.loads(resp.get("result", {}).get("result", {}).get("value", "[]"))
    
    print(f"\n  Frame-level arm jumps detected: {len(jumps)}")
    if jumps:
        print("  Jump details (first 10):")
        for j in jumps[:10]:
            print(f"    Frame {j['frame']}: {j['bone']} diff={j['diff']}")
            print(f"      Before: {j['before']}")
            print(f"      After:  {j['after']}")
    
    # Also get mixer actions state
    resp = cdp(ws, "Runtime.evaluate", {
        "expression": """
        (function() {
            const mixer = window.__test.mixer;
            if (!mixer) return JSON.stringify({error: 'no mixer'});
            const actions = [];
            mixer._actions.forEach(a => {
                actions.push({
                    name: a._clip?.name,
                    weight: a.getEffectiveWeight(),
                    running: a.isRunning(),
                    trackCount: a._clip?.tracks?.length,
                    tracks: a._clip?.tracks?.map(t => (t.name.match(/bones\\[(.+?)\\]/)||[])[1]).join(',')
                });
            });
            return JSON.stringify(actions);
        })()
        """,
        "returnByValue": True
    })
    actions = json.loads(resp.get("result", {}).get("result", {}).get("value", "[]"))
    print(f"\n  Mixer actions after execution:")
    for a in actions:
        print(f"    {a.get('name', '?')}: weight={a.get('weight')} running={a.get('running')} tracks={a.get('trackCount')} bones={a.get('tracks')}")
    
    # Final verdict
    print("\n" + "="*60)
    arm_jumps_detected = len(jumps) > 0
    arm_diffs = {k: v for k, v in result.get("diffs", {}).items() 
                 if k in ['右腕', '左腕', '右肩', '左肩', '右ひじ', '左ひじ', '右手首', '左手首']}
    significant_arm_diffs = {k: v for k, v in arm_diffs.items() if v > 0.01}
    
    if arm_jumps_detected:
        print(f"🔴 FAIL: {len(jumps)} frame-level arm jumps detected!")
    elif significant_arm_diffs:
        print(f"🔴 FAIL: Significant arm bone changes detected: {significant_arm_diffs}")
    else:
        print("✅ PASS: No arm bone jumps detected during nod animation")
    
    if track_data.get('allBoneNames'):
        arm_tracks = [b for b in track_data['allBoneNames'] 
                     if any(a in b for a in ['腕', '肩', 'ひじ', '手首'])]
        if arm_tracks:
            print(f"⚠️  Note: VMD contains arm tracks: {arm_tracks}")
            print("   (keepIdle filter should prevent these from playing)")
    
    print("="*60)
    
    # Cleanup
    ws.close()
    chrome_proc.kill()
    chrome_proc.wait()
    server.kill()
    server.wait()

if __name__ == "__main__":
    msg_id = 0
    main()
