import os
import re
import json
import datetime

# Reuse the parser logic from battery_guardian_web.py
def parse_ioreg(text):
    d = {}
    for m in re.finditer(r'"(\w+)"\s*=\s*(\d+)', text):
        d[m.group(1)] = int(m.group(2))
    for m in re.finditer(r'"(\w+)"\s*=\s*"([^"]+)"', text):
        d[m.group(1)] = m.group(2)
    # Lists
    for m in re.finditer(r'"(\w+)"\s*=\s*\(([^)]+)\)', text):
        content = m.group(2)
        try:
            vals = [int(x.strip()) for x in content.split(',') if x.strip().isdigit()]
            if vals: d[m.group(1)] = vals
        except: pass
    return d

def strip_rtf(text):
    # Very basic RTF stripper (removing control words)
    text = re.sub(r'\\[a-z]+\-?[0-9]* ?', '', text)
    # text = re.sub(r'\{.*?\}', '', text)  <-- REMOVED: ioreg uses {} for dicts, we need them!
    # Instead, remove specifically RTF header blocks if we can identify them?
    # Or just rely on the fact that ioreg {} are balanced and might contain data.
    # The previous line was nuking "LifetimeData" = {...}
    
    # Let's just remove specific RTF noise left over
    text = text.replace("\\", "")
    return text

def ingest():
    base_dir = "."
    all_logs = []
    
    # Walk through all subdirectories (Ebuka, Caleb, etc)
    for root, dirs, files in os.walk(base_dir):
        for file in files:
            if file.endswith(".rtf") or file.endswith(".txt"):
                path = os.path.join(root, file)
                print(f"Processing: {path}")
                
                try:
                    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                        raw = f.read()
                        
                    # Clean RTF junk if needed
                    if file.endswith(".rtf"):
                        clean_text = strip_rtf(raw)
                    else:
                        clean_text = raw
                        
                    # Find ioreg blocks
                    # Looking for the start of an ioreg dump
                    blocks = re.split(r'\+-o AppleSmartBattery', clean_text)
                    
                    for block in blocks[1:]: # Skip preamble
                        # Parsing Timestamp from the chat line before the block?
                        # It's hard because split removes the delimiter. 
                        # Let's try to match Timestamp + Block together.
                        pass 

                    # Better approach: Iterate matches
                    # Chat Format: "Name, [Date Time] ... content"
                    entry_pattern = r'\[(\d{1,2}/\d{1,2}/\d{2,4}),?\s+(\d{1,2}:\d{2})\s?([AP]M)\]'
                    
                    # Split by the specific ioreg starter but try to capture the preceding lines
                    # Actually, standard split strategies are hard with chat logs.
                    # Let's assume one file = one timestamp? No, multiple entries per file possible.
                    
                    # Heuristic: The timestamp usually appears within 100-200 chars BEFORE the "+-o AppleSmartBattery"
                    matches = list(re.finditer(r'\+-o AppleSmartBattery', clean_text))
                    
                    for i, match in enumerate(matches):
                        start_idx = match.start()
                        # Search backwards for timestamp
                        search_window = clean_text[max(0, start_idx-200):start_idx]
                        ts_match = re.search(entry_pattern, search_window)
                        
                        log_time = datetime.datetime.now() # Fallback
                        if ts_match:
                            d, t, ampm = ts_match.groups()
                            # Parse "1/20/26 1:07 PM"
                            dt_str = f"{d} {t} {ampm}"
                            try:
                                log_time = datetime.datetime.strptime(dt_str, "%m/%d/%y %I:%M %p")
                            except:
                                try:
                                     # Try 4 digit year
                                     log_time = datetime.datetime.strptime(dt_str, "%m/%d/%Y %I:%M %p")
                                except: pass
                        
                        # Extract the block content (until next block or end)
                        end_idx = matches[i+1].start() if i < len(matches)-1 else len(clean_text)
                        block_content = clean_text[start_idx:end_idx]
                        
                        parsed = parse_ioreg(block_content)
                        
                        if "CycleCount" in parsed or "MaxCapacity" in parsed:
                            entry = {
                                "source_file": file,
                                "volunteer": os.path.basename(root),
                                "timestamp": log_time.isoformat(),
                                "parsed": parsed
                            }
                            all_logs.append(entry)
                            print(f"  -> Found Log per {log_time}: Cycles={parsed.get('CycleCount')}")
                            
                except Exception as e:
                    print(f"  [!] Error reading {file}: {e}")

    # Save to unified JSON
    with open("control_group.json", "w") as f:
        json.dump(all_logs, f, indent=2)
    
    print(f"\n[=] Ingestion Complete. Saved {len(all_logs)} snapshots to control_group.json")

if __name__ == "__main__":
    ingest()
