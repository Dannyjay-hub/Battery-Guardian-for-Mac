/**
 * Battery Guardian download analytics and Intel data collection Worker.
 *
 * TG_BOT_TOKEN and TG_CHAT_ID are Cloudflare secret bindings. Never place
 * either value in this file or commit them to the repository.
 */

var GITHUB_BASE = "https://github.com/Dannyjay-hub/Battery-Guardian-for-Mac/releases/download/v1.4";
var ASSETS = {
  silicon: "Battery_Guardian_v1.4_AppleSilicon.zip",
  intel: "BatteryGuardian_v1.3.2_Intel.dmg"
};

var CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type"
};

async function notifyTelegram(text) {
  try {
    await fetch("https://api.telegram.org/bot" + TG_BOT_TOKEN + "/sendMessage", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: TG_CHAT_ID, text: text, parse_mode: "HTML" })
    });
  } catch (e) {}
}

function parseOS(ua) {
  if (!ua) return "Unknown";
  var mac = ua.match(/Mac OS X ([\d_]+)/);
  if (mac) return "macOS " + mac[1].replace(/_/g, ".");
  if (ua.indexOf("Windows") >= 0) return "Windows";
  if (ua.indexOf("Linux") >= 0) return "Linux";
  return "Other";
}

async function recordDownload(data) {
  try {
    var totalKey = "total:" + data.platform;
    var previousTotal = parseInt(await ANALYTICS.get(totalKey) || "0");
    await ANALYTICS.put(totalKey, String(previousTotal + 1));

    var countryKey = "country:" + data.platform + ":" + data.country;
    var previousCountry = parseInt(await ANALYTICS.get(countryKey) || "0");
    await ANALYTICS.put(countryKey, String(previousCountry + 1));

    var osKey = "os:" + data.platform + ":" + data.os.replace(/\s/g, "_");
    var previousOS = parseInt(await ANALYTICS.get(osKey) || "0");
    await ANALYTICS.put(osKey, String(previousOS + 1));

    var dayKey = "day:" + data.platform + ":" + data.dateKey;
    var previousDay = parseInt(await ANALYTICS.get(dayKey) || "0");
    await ANALYTICS.put(dayKey, String(previousDay + 1));

    var logKey = "log:" + data.platform;
    var logRaw = await ANALYTICS.get(logKey);
    var log = logRaw ? JSON.parse(logRaw) : [];
    log.unshift({
      ts: data.ts,
      country: data.country,
      os: data.os,
      ref: data.referrer.slice(0, 100)
    });
    if (log.length > 200) log.length = 200;
    await ANALYTICS.put(logKey, JSON.stringify(log));
  } catch (e) {}
}

async function handleAnalytics() {
  var totalSilicon = parseInt(await ANALYTICS.get("total:silicon") || "0");
  var totalIntel = parseInt(await ANALYTICS.get("total:intel") || "0");
  var logSilicon = await ANALYTICS.get("log:silicon");
  var logIntel = await ANALYTICS.get("log:intel");
  var list = await ANALYTICS.list();
  var countries = {};
  var operatingSystems = {};
  var daily = {};

  for (var index = 0; index < list.keys.length; index++) {
    var key = list.keys[index].name;
    var value = parseInt(await ANALYTICS.get(key) || "0");
    if (key.indexOf("country:") === 0) {
      var country = key.split(":")[2];
      countries[country] = (countries[country] || 0) + value;
    }
    if (key.indexOf("os:") === 0) {
      var os = key.split(":")[2].replace(/_/g, " ");
      operatingSystems[os] = (operatingSystems[os] || 0) + value;
    }
    if (key.indexOf("day:") === 0) {
      var day = key.split(":")[2];
      daily[day] = (daily[day] || 0) + value;
    }
  }

  var result = {
    totals: { silicon: totalSilicon, intel: totalIntel, combined: totalSilicon + totalIntel },
    breakdown: { countries: countries, os: operatingSystems, daily: daily },
    recent: {
      silicon: logSilicon ? JSON.parse(logSilicon).slice(0, 20) : [],
      intel: logIntel ? JSON.parse(logIntel).slice(0, 20) : []
    }
  };

  return new Response(JSON.stringify(result, null, 2), {
    headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" }
  });
}

async function hashContent(text) {
  var encoder = new TextEncoder();
  var data = encoder.encode(text);
  var hashBuffer = await crypto.subtle.digest("SHA-256", data);
  var hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map(function (byte) {
    return byte.toString(16).padStart(2, "0");
  }).join("");
}

function detectChipType(ioreg) {
  var hasSilicon = ioreg.indexOf("CycleCountLastQmax") !== -1 || ioreg.indexOf("MaximumPackVoltage") !== -1;
  var hasIntel = ioreg.indexOf("DesignCycleCount70") !== -1 || ioreg.indexOf("PackReserve") !== -1;
  if (hasSilicon && !hasIntel) return "silicon";
  if (hasIntel && !hasSilicon) return "intel";
  return "unknown";
}

async function handleIntelSubmit(request) {
  try {
    var body = await request.json();
    var ioreg = body.ioreg || "";
    var label = body.label || "unknown";
    var timestamp = body.ts || new Date().toISOString();

    if (ioreg.length < 50) {
      return new Response(JSON.stringify({ error: "Data too short" }), {
        status: 400,
        headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" }
      });
    }

    var contentHash = await hashContent(ioreg);
    var duplicateKey = "intel-hash:" + contentHash;
    var existing = await ANALYTICS.get(duplicateKey);
    if (existing) {
      var existingData = JSON.parse(existing);
      return new Response(JSON.stringify({
        error: "duplicate",
        message: "This exact battery data was already submitted on " + existingData.ts.slice(0, 10) + ". Thank you!",
        count: parseInt(await ANALYTICS.get("intel-submissions-count") || "0")
      }), {
        status: 409,
        headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" }
      });
    }

    var country = request.headers.get("CF-IPCountry") || "XX";
    var chipType = detectChipType(ioreg);
    var currentCount = parseInt(await ANALYTICS.get("intel-submissions-count") || "0");
    var newCount = currentCount + 1;
    await ANALYTICS.put("intel-submissions-count", String(newCount));

    var submissionKey = "intel-sub:" + String(newCount).padStart(6, "0");
    await ANALYTICS.put(submissionKey, JSON.stringify({
      ts: timestamp,
      country: country,
      label: label,
      chipType: chipType,
      hash: contentHash.slice(0, 12),
      ioreg: ioreg
    }));
    await ANALYTICS.put(duplicateKey, JSON.stringify({ id: newCount, ts: timestamp }));

    var sizeKB = (ioreg.length / 1024).toFixed(1);
    var message = "\u{1F4E6} <b>New battery submission #" + newCount + "</b>\n"
      + "\u{1F30D} Country: " + country + "\n"
      + "\u{1F3F7} Label: " + label + "\n"
      + "\u{1F4BB} Chip: " + chipType + "\n"
      + "\u{1F4CF} Size: " + sizeKB + " KB";
    await notifyTelegram(message);

    var metadataKey = "intel-submissions-meta";
    var metadataRaw = await ANALYTICS.get(metadataKey);
    var metadata = metadataRaw ? JSON.parse(metadataRaw) : [];
    metadata.unshift({
      id: newCount,
      ts: timestamp,
      country: country,
      label: label,
      chipType: chipType,
      length: ioreg.length
    });
    if (metadata.length > 50) metadata.length = 50;
    await ANALYTICS.put(metadataKey, JSON.stringify(metadata));

    return new Response(JSON.stringify({ success: true, count: newCount }), {
      headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" }
    });
  } catch (e) {
    return new Response(JSON.stringify({ error: "Invalid request" }), {
      status: 400,
      headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" }
    });
  }
}

async function handleIntelCount() {
  var count = parseInt(await ANALYTICS.get("intel-submissions-count") || "0");
  return new Response(JSON.stringify({ count: count }), {
    headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" }
  });
}

async function handleIntelList() {
  var metadataRaw = await ANALYTICS.get("intel-submissions-meta");
  var metadata = metadataRaw ? JSON.parse(metadataRaw) : [];
  return new Response(JSON.stringify({ submissions: metadata }), {
    headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" }
  });
}

addEventListener("fetch", function (event) {
  event.respondWith(handleRequest(event.request, event));
});

async function handleRequest(request, event) {
  var url = new URL(request.url);
  var path = url.pathname.toLowerCase();

  if (request.method === "OPTIONS") {
    return new Response(null, { headers: CORS_HEADERS });
  }

  if (path === "/analytics" || path === "/analytics/") {
    return handleAnalytics();
  }

  if (path === "/submit/intel" || path === "/submit/intel/") {
    if (request.method === "POST") return handleIntelSubmit(request);
    return new Response("POST only", { status: 405 });
  }

  if (path === "/submit/intel/count" || path === "/submit/intel/count/") {
    return handleIntelCount();
  }

  if (path === "/submit/intel/list" || path === "/submit/intel/list/") {
    return handleIntelList();
  }

  var platform = null;
  if (path.indexOf("/download/silicon") === 0) platform = "silicon";
  if (path.indexOf("/download/intel") === 0) platform = "intel";

  if (!platform) {
    return new Response(
      "Battery Guardian Worker\n\n/download/silicon\n/download/intel\n/analytics\n/submit/intel (POST)\n/submit/intel/count\n/submit/intel/list",
      { status: 200, headers: { "Content-Type": "text/plain" } }
    );
  }

  var country = request.headers.get("CF-IPCountry") || "XX";
  var userAgent = request.headers.get("User-Agent") || "";
  var referrer = request.headers.get("Referer") || "Direct";
  var os = parseOS(userAgent);
  var timestamp = new Date().toISOString();
  var dateKey = timestamp.slice(0, 10);

  event.waitUntil(recordDownload({
    ts: timestamp,
    country: country,
    platform: platform,
    os: os,
    referrer: referrer,
    dateKey: dateKey
  }));

  return Response.redirect(GITHUB_BASE + "/" + ASSETS[platform], 302);
}
