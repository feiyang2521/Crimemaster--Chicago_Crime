#!/usr/bin/env python3
"""Build index.html with all libraries embedded inline (no CDN dependency)."""
import json, os, base64

BASE = os.path.dirname(__file__) or "."

# --- Download CDN libs locally if not present ---
def ensure(path, url):
    if not os.path.exists(path):
        import urllib.request
        print(f"  Downloading {url}...")
        urllib.request.urlretrieve(url, path)
    sz = os.path.getsize(path)
    print(f"  {os.path.basename(path)}: {sz//1024} KB")

leaflet_js  = os.path.join(BASE, "leaflet.js")
leaflet_css = os.path.join(BASE, "leaflet.css")
d3_js       = os.path.join(BASE, "d3.min.js")

print("Checking local library files...")
ensure(leaflet_js,  "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js")
ensure(leaflet_css, "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css")
ensure(d3_js,       "https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js")

# --- Read all data ---
with open(os.path.join(BASE, "crime_data.json"), encoding="utf-8") as f:
    D = json.load(f)
with open(os.path.join(BASE, "comm_geo.json"), encoding="utf-8") as f:
    C = json.load(f)
with open(os.path.join(BASE, "dist_geo.json"), encoding="utf-8") as f:
    DG = json.load(f)
with open(leaflet_js,  encoding="utf-8") as f: leaflet_src  = f.read()
with open(leaflet_css, encoding="utf-8") as f: leaflet_css_src = f.read()
with open(d3_js,       encoding="utf-8") as f: d3_src       = f.read()

POLICE = [
    {"name":"1st District (Central)","lat":41.8827,"lng":-87.6273},
    {"name":"2nd District (Wentworth)","lat":41.8084,"lng":-87.6131},
    {"name":"3rd District (Grand Crossing)","lat":41.7473,"lng":-87.6051},
    {"name":"4th District (South Chicago)","lat":41.7251,"lng":-87.5548},
    {"name":"5th District (Calumet)","lat":41.7308,"lng":-87.6182},
    {"name":"6th District (Gresham)","lat":41.7488,"lng":-87.6551},
    {"name":"7th District (Englewood)","lat":41.7831,"lng":-87.6426},
    {"name":"8th District (Chicago Lawn)","lat":41.7848,"lng":-87.7050},
    {"name":"9th District (Deering)","lat":41.8333,"lng":-87.6651},
    {"name":"10th District (Ogden)","lat":41.8511,"lng":-87.6715},
    {"name":"11th District (Harrison)","lat":41.8600,"lng":-87.6306},
    {"name":"12th District (Near West)","lat":41.8812,"lng":-87.6689},
    {"name":"14th District (Shakespeare)","lat":41.9100,"lng":-87.6443},
    {"name":"15th District (Austin)","lat":41.8700,"lng":-87.7600},
    {"name":"16th District (Jefferson Park)","lat":41.9710,"lng":-87.7978},
    {"name":"17th District (Albany Park)","lat":41.9640,"lng":-87.7231},
    {"name":"18th District (Near North)","lat":41.9007,"lng":-87.6347},
    {"name":"19th District (Town Hall)","lat":41.9478,"lng":-87.6509},
    {"name":"20th District (Morgan Park)","lat":41.6911,"lng":-87.6718},
    {"name":"22nd District","lat":41.7233,"lng":-87.6610},
    {"name":"24th District (Rogers Park)","lat":41.9833,"lng":-87.6752},
    {"name":"25th District (Grand Central)","lat":41.8850,"lng":-87.7833},
    {"name":"31st District (O'Hare)","lat":41.9800,"lng":-87.9100},
]

crime_json  = json.dumps(D,  separators=(',', ':'))
comm_json   = json.dumps(C,  separators=(',', ':'))
dist_json   = json.dumps(DG, separators=(',', ':'))
police_json = json.dumps(POLICE, separators=(',', ':'))

# --- Build data-URI versions for self-contained HTML ---
leaflet_css_b64 = base64.b64encode(leaflet_css_src.encode()).decode()
d3_b64          = base64.b64encode(d3_src.encode()).decode()
leaflet_js_b64  = base64.b64encode(leaflet_src.encode()).decode()

print(f"crime_data JSON:  {len(crime_json)//1024} KB")
print(f"comm_geo JSON:    {len(comm_json)//1024} KB")
print(f"dist_geo JSON:    {len(dist_json)//1024} KB")

# --- JavaScript code ---
JS = """
// ============================================================
// CONSTANTS & STATE
// ============================================================
var SEVERITY = {
    "HOMICIDE":10,"KIDNAPPING":9,"HUMAN TRAFFICKING":9,
    "ROBBERY":8,"SEX OFFENSE":8,"CRIM SEXUAL ASSAULT":8,
    "ASSAULT":7,"BATTERY":7,"STALKING":7,
    "BURGLARY":6,"ARSON":6,
    "MOTOR VEHICLE THEFT":5,"WEAPONS VIOLATION":5,"INTIMIDATION":5,
    "THEFT":4,"DECEPTIVE PRACTICE":4,
    "CRIMINAL DAMAGE":3,"OFFENSE INVOLVING CHILDREN":3,
    "CRIMINAL TRESPASS":2,"LIQUOR LAW VIOLATION":2,"NARCOTICS":2,"OTHER NARCOTIC VIOLATION":2,
};

var MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
var COLORS = ["#276749","#48bb78","#d69e2e","#dd6b20","#e53e3e","#8B0000"];

var map, commLayer, distLayer;
var policeMarkers = [];
var userMarker = null;
var policeLines = [];
var D = null;
var C = null;
var VIEW = 'district'; // current level: 'district' | 'community'

var F = {
    yearLo: 2001, yearHi: 2026,
    monthLo: 1,    monthHi: 12,
    hourLo: 0,     hourHi: 23,
    district: null
};

var allCrimeTypes = [];
var CT_SELECTED = new Set();
var clickMode = false;
var crimeDotMarkers = [];

// ============================================================
// UTILITIES
// ============================================================
function sev(t) { return SEVERITY[t] || 1; }

function riskColor(score) {
    if (score > 0.8) return COLORS[5];
    if (score > 0.6) return COLORS[4];
    if (score > 0.4) return COLORS[3];
    if (score > 0.2) return COLORS[2];
    return COLORS[1];
}

function haversine(lat1, lng1, lat2, lng2) {
    var R = 6371;
    var dLat = (lat2 - lat1) * Math.PI / 180;
    var dLng = (lng2 - lng1) * Math.PI / 180;
    var a = Math.sin(dLat/2)*Math.sin(dLat/2) +
            Math.cos(lat1*Math.PI/180)*Math.cos(lat2*Math.PI/180)*
            Math.sin(dLng/2)*Math.sin(dLng/2);
    return R * 2 * Math.asin(Math.sqrt(a));
}

function setLoading(msg, pct) {
    var t = document.getElementById('loading-text');
    var b = document.getElementById('loading-bar');
    if (t) t.textContent = msg;
    if (b) b.style.width = pct + '%';
}

// ============================================================
// DATA HELPERS — bidirectional cross-filtering
// ============================================================
function getTypeCounts() {
    var types = CT_SELECTED.size > 0 ? [...CT_SELECTED] : allCrimeTypes;
    var result = {};
    types.forEach(function(t){ result[t] = 0; });

    var yl = F.yearLo, yh = F.yearHi, ml = F.monthLo, mh = F.monthHi, hl = F.hourLo, hh = F.hourHi;

    for (var y = yl; y <= yh; y++) {
        var yd = D.ym_type[String(y)];
        if (!yd) continue;
        for (var m = ml; m <= mh; m++) {
            var md = yd[String(m)];
            if (!md) continue;
            for (var t of types) {
                result[t] += (md[t] || 0);
            }
        }
    }
    // Add hour dimension
    for (var h = hl; h <= hh; h++) {
        var hd = D.hour_type[String(h)];
        if (!hd) continue;
        for (var t of types) {
            result[t] += (hd[t] || 0);
        }
    }
    return result;
}

function getYearData() {
    if (F.district && D.dist_agg[F.district]) {
        return D.dist_agg[F.district].by_year || {};
    }
    // Return ym_type aggregated by year for the selected months+hours
    var ml = F.monthLo, mh = F.monthHi, hl = F.hourLo, hh = F.hourHi;
    var result = {};
    var yl = F.yearLo, yh = F.yearHi;
    for (var y = yl; y <= yh; y++) {
        var cnt = 0;
        var yd = D.ym_type[String(y)];
        if (yd) {
            for (var m = ml; m <= mh; m++) {
                var md = yd[String(m)];
                if (md) {
                    for (var t in md) cnt += md[t] || 0;
                }
            }
        }
        // Multiply by hour proportion
        var hd = D.hour_type;
        var totalHour = 0, selHour = 0;
        for (var h = 0; h <= 23; h++) {
            var hdata = hd[String(h)];
            if (hdata) {
                for (var t in hdata) totalHour += hdata[t] || 0;
                if (h >= hl && h <= hh) {
                    for (var t in hdata) selHour += hdata[t] || 0;
                }
            }
        }
        if (totalHour > 0) cnt = Math.round(cnt * selHour / totalHour);
        result[y] = cnt;
    }
    return result;
}

function getMonthData() {
    if (F.district && D.dist_agg[F.district]) {
        return D.dist_agg[F.district].by_month || {};
    }
    var yl = F.yearLo, yh = F.yearHi, hl = F.hourLo, hh = F.hourHi;
    var result = {};
    for (var m = 1; m <= 12; m++) {
        var cnt = 0;
        for (var y = yl; y <= yh; y++) {
            var yd = D.ym_type[String(y)];
            if (yd) {
                var md = yd[String(m)];
                if (md) for (var t in md) cnt += md[t] || 0;
            }
        }
        // Adjust by hour filter
        var hd = D.hour_type;
        var totalHour = 0, selHour = 0;
        for (var h = 0; h <= 23; h++) {
            var hdata = hd[String(h)];
            if (hdata) { for (var t in hdata) totalHour += hdata[t]||0; if (h>=hl&&h<=hh) for (var t in hdata) selHour += hdata[t]||0; }
        }
        if (totalHour > 0) cnt = Math.round(cnt * selHour / totalHour);
        result[m] = cnt;
    }
    return result;
}

function getHourData() {
    if (F.district && D.dist_agg[F.district]) {
        return D.dist_agg[F.district].by_hour || {};
    }
    var yl = F.yearLo, yh = F.yearHi, ml = F.monthLo, mh = F.monthHi;
    var result = {};
    for (var h = 0; h <= 23; h++) {
        var hd = D.hour_type[String(h)];
        if (hd) {
            var cnt = 0;
            for (var y = yl; y <= yh; y++) {
                var yd = D.ym_type[String(y)];
                if (yd) {
                    for (var m = ml; m <= mh; m++) {
                        var md = yd[String(m)];
                        if (md) {
                            for (var t in md) {
                                var v = hd[t];
                                if (v) cnt += v;
                            }
                        }
                    }
                }
            }
            result[h] = cnt;
        } else {
            result[h] = 0;
        }
    }
    return result;
}

// ============================================================
// CRIME TYPE FILTER
// ============================================================
function renderCrimeTypeFilter() {
    var counts = getTypeCounts();
    var total = 0;
    for (var k in counts) total += counts[k];
    var sorted = Object.entries(counts).sort(function(a,b){ return b[1]-a[1]; });
    var container = document.getElementById('crime-type-list');
    container.innerHTML = '';

    var header = document.createElement('div');
    header.style.cssText = 'display:flex;gap:6px;margin-bottom:8px;';

    var allBtn = document.createElement('button');
    allBtn.textContent = 'All';
    allBtn.style.cssText = 'font-size:10px;padding:2px 8px;background:#1e2535;border:1px solid #2d4f7c;color:#4299e1;border-radius:4px;cursor:pointer;';
    allBtn.onclick = function() {
        CT_SELECTED = new Set(allCrimeTypes);
        renderCrimeTypeFilter();
        updateAll();
    };

    var noneBtn = document.createElement('button');
    noneBtn.textContent = 'None';
    noneBtn.style.cssText = 'font-size:10px;padding:2px 8px;background:#1e2535;border:1px solid #2d4f7c;color:#718096;border-radius:4px;cursor:pointer;';
    noneBtn.onclick = function() {
        CT_SELECTED = new Set();
        renderCrimeTypeFilter();
        updateAll();
    };

    header.appendChild(allBtn);
    header.appendChild(noneBtn);
    container.appendChild(header);

    sorted.forEach(function(item) {
        var type = item[0], count = item[1];
        var pct = total > 0 ? (count / total * 100).toFixed(1) : '0.0';
        var checked = CT_SELECTED.has(type);
        var el = document.createElement('div');
        el.className = 'crime-type-item';
        el.innerHTML =
            '<input type="checkbox"' + (checked ? ' checked' : '') + ' data-type="' + type + '">' +
            '<span class="ct-label">' + type + '</span>' +
            '<div class="ct-bar-wrap"><div class="ct-bar" style="width:' + Math.max(1, pct) + '%"></div></div>' +
            '<span class="ct-count">' + count.toLocaleString() + '</span>';
        el.querySelector('input').addEventListener('change', function(e) {
            if (e.target.checked) CT_SELECTED.add(type); else CT_SELECTED.delete(type);
            renderCrimeTypeFilter();
            updateAll();
        });
        container.appendChild(el);
    });
}

// ============================================================
// DISTRICT FILTER
// ============================================================
function renderDistrictFilter() {
    var container = document.getElementById('district-list');
    container.innerHTML = '';
    var distIds = Object.keys(D.dist_agg).sort(function(a,b){ return parseInt(a)-parseInt(b); });

    distIds.forEach(function(d) {
        var info = D.dist_risk[d] || {};
        var name = info.name || ('District ' + d);
        var active = F.district === d;
        var el = document.createElement('div');
        el.className = 'dist-item' + (active ? ' active' : '');
        el.dataset.id = d;
        el.innerHTML = '<span>' + name + '</span><span class="dist-badge">' + (info.total||0).toLocaleString() + '</span>';
        el.addEventListener('click', function() {
            if (F.district === d) { clearDistrict(); }
            else { F.district = d; renderDistrictFilter(); enterDrilldown(d); }
        });
        container.appendChild(el);
    });
}

function clearDistrict() {
    F.district = null;
    renderDistrictFilter();
    exitDrilldown();
}

// ============================================================
// CHARTS (D3)
// ============================================================
function drawChart(svgId, data, selLo, selHi, onClick) {
    var wrap = document.getElementById(svgId);
    if (!wrap) return;
    var W = wrap.clientWidth || 200;
    var H = wrap.clientHeight || 80;
    wrap.innerHTML = '';
    var svg = d3.select(wrap).append('svg').attr('width', W).attr('height', H);

    var keys = Object.keys(data).sort(function(a,b){ return parseInt(a)-parseInt(b); });
    var maxVal = 1;
    keys.forEach(function(k){ if(data[k] > maxVal) maxVal = data[k]; });

    var bw = Math.max(2, (W / keys.length) - 1);
    var x = d3.scaleLinear().domain([0, keys.length]).range([0, W]);
    var y = d3.scaleLinear().domain([0, maxVal]).range([H-2, 2]);

    keys.forEach(function(k, i) {
        var v = data[k] || 0;
        var xi = x(i);
        var barH = H - y(v);
        var inRange = parseInt(k) >= selLo && parseInt(k) <= selHi;

        svg.append('rect')
          .attr('x', xi).attr('y', H - barH)
          .attr('width', bw).attr('height', barH)
          .attr('fill', inRange ? '#4299e1' : '#2d4f7c')
          .attr('rx', 1)
          .style('cursor', 'pointer')
          .on('click', function() { onClick(k); })
          .on('dblclick', function() { onClick(null); });
    });
}

function updateCharts() {
    var yData = getYearData();
    var mData = getMonthData();
    var hData = getHourData();

    var yearClick = function(val) {
        if (val === null) {
            F.yearLo = 2001; F.yearHi = 2026;
        } else {
            var v = parseInt(val);
            if (F.yearLo === v && F.yearHi === v) {
                F.yearLo = 2001; F.yearHi = 2026;
            } else {
                F.yearLo = v; F.yearHi = v;
            }
        }
        updateAll();
    };

    var monthClick = function(val) {
        if (val === null) {
            F.monthLo = 1; F.monthHi = 12;
        } else {
            var v = parseInt(val);
            if (F.monthLo === v && F.monthHi === v) {
                F.monthLo = 1; F.monthHi = 12;
            } else {
                F.monthLo = v; F.monthHi = v;
            }
        }
        updateAll();
    };

    var hourClick = function(val) {
        if (val === null) {
            F.hourLo = 0; F.hourHi = 23;
        } else {
            var v = parseInt(val);
            if (F.hourLo === v && F.hourHi === v) {
                F.hourLo = 0; F.hourHi = 23;
            } else {
                F.hourLo = v; F.hourHi = v;
            }
        }
        updateAll();
    };

    drawChart('svg-year',  yData, F.yearLo,  F.yearHi,  yearClick);
    drawChart('svg-month', mData, F.monthLo, F.monthHi, monthClick);
    drawChart('svg-hour',  hData, F.hourLo,  F.hourHi,  hourClick);

    var mLbl = document.getElementById('lbl-month');
    var hLbl = document.getElementById('lbl-hour');
    var yLbl = document.getElementById('lbl-year');
    if (mLbl) mLbl.textContent = MONTHS[F.monthLo-1] + '-' + MONTHS[F.monthHi-1];
    if (hLbl) hLbl.textContent = (F.hourLo<10?'0':'') + F.hourLo + '-' + (F.hourHi<10?'0':'') + F.hourHi;
    if (yLbl) yLbl.textContent = F.yearLo + '-' + F.yearHi;
}

// ============================================================
// SLIDERS
// ============================================================
function initSliders() {
    initSlider('year',  2001, 2026, function(){ F.yearLo=this.lo; F.yearHi=this.hi; updateAll(); });
    initSlider('month', 1,    12,   function(){ F.monthLo=this.lo; F.monthHi=this.hi; updateAll(); });
    initSlider('hour',  0,    23,   function(){ F.hourLo=this.lo; F.hourHi=this.hi; updateAll(); });
}

function initSlider(id, min, max, onChange) {
    var lo = id + 'Lo', hi = id + 'Hi';
    var track = document.getElementById('track-' + id);
    var fill  = document.getElementById('fill-' + id);
    var loT   = document.getElementById('thumb-' + id + '-lo');
    var hiT   = document.getElementById('thumb-' + id + '-hi');
    var dragging = null;
    var self = { lo: F[lo], hi: F[hi] };

    function pos() {
        var p = function(v){ return ((v-min)/(max-min))*100; };
        if (fill) { fill.style.left = p(self.lo) + '%'; fill.style.width = (p(self.hi) - p(self.lo)) + '%'; }
        if (loT) loT.style.left = p(self.lo) + '%';
        if (hiT) hiT.style.left = p(self.hi) + '%';
    }
    if (track) pos();

    function getVal(clientX) {
        var r = track.getBoundingClientRect();
        return Math.round(min + (max-min) * (clientX - r.left) / r.width);
    }

    [loT, hiT].forEach(function(th){
        if (!th) return;
        th.addEventListener('mousedown', function(e){ dragging = th; th.classList.add('active'); e.preventDefault(); });
    });

    document.addEventListener('mousemove', function(e){
        if (!dragging) return;
        var v = Math.max(min, Math.min(max, getVal(e.clientX)));
        if (dragging === loT) self.lo = Math.min(v, self.hi);
        else                  self.hi = Math.max(v, self.lo);
        pos();
    });

    document.addEventListener('mouseup', function(){
        if (dragging) {
            dragging.classList.remove('active');
            dragging = null;
            F[lo] = self.lo; F[hi] = self.hi;
            onChange.call(self);
        }
    });
}

// ============================================================
// MAP LAYERS
// ============================================================
function initMap() {
    setLoading("Initializing map...", 50);
    try {
        map = L.map('map', { zoomControl: true }).setView([41.83, -87.68], 10);
    } catch(e) {
        setLoading("Error: " + e.message, 100);
        return;
    }
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '© OpenStreetMap © CartoDB', maxZoom: 19
    }).addTo(map);

    setLoading("Loading district boundaries...", 60);
    distLayer = L.geoJSON(window.__DIST_GEO__, {
        style: function(feat) {
            var d = String(feat.properties.dist_num);
            var risk = D.dist_risk[d];
            return {
                fillColor: riskColor(risk ? risk.score : 0),
                fillOpacity: 0.75,
                weight: 1.5,
                color: '#2d4f7c'
            };
        },
        onEachFeature: function(feat, layer) {
            var d = String(feat.properties.dist_num);
            var info = D.dist_risk[d] || {};
            var name = info.name || ('District ' + d);
            var total = info.total || 0;
            var score = (info.score || 0).toFixed(3);
            layer.bindTooltip(
                '<div class="tt-title">' + name + '</div>' +
                '<div class="tt-row"><span class="tt-lbl">Risk Score</span><span class="tt-pct">' + score + '</span></div>' +
                '<div class="tt-row"><span class="tt-lbl">Total Crimes</span><span class="tt-pct">' + total.toLocaleString() + '</span></div>',
                { className: 'ct-tooltip', sticky: true }
            );
            layer.on('click', function() {
                F.district = d;
                renderDistrictFilter();
                enterDrilldown(d);
            });
        }
    }).addTo(map);

    setLoading("Loading community boundaries...", 70);
    commLayer = L.geoJSON(window.__COMM_GEO__, {
        style: { fillColor: '#2d4f7c', fillOpacity: 0, weight: 0.5, color: '#1e2535' },
        onEachFeature: function(feat, layer) {
            var cid = String(feat.properties.area_num_1);
            var info = D.comm_risk[cid] || {};
            var name = info.name || ('Community ' + cid);

            layer.on({
                mouseover: function(e) {
                    var l = e.target;
                    l.setStyle({ fillOpacity: 0.5, weight: 2, color: '#fff' });
                    var ct = D.comm_type[cid] || {};
                    var total = 0;
                    for (var k in ct) total += ct[k];
                    total = total || 1;
                    var top5 = Object.entries(ct).sort(function(a,b){return b[1]-a[1];}).slice(0,5);
                    var rows = '';
                    top5.forEach(function(item){
                        rows += '<div class="tt-row"><span class="tt-lbl">' + item[0] + '</span><span class="tt-pct">' + (item[1]/total*100).toFixed(1) + '%</span></div>';
                    });
                    layer.bindTooltip(
                        '<div class="tt-title">' + name + '</div>' + rows +
                        '<div class="tt-total">Total: ' + total.toLocaleString() + '</div>',
                        { className: 'ct-tooltip', sticky: true, offset: [12, 0] }
                    ).openTooltip(e.latlng);
                },
                mouseout: function(e) {
                    var opacity = VIEW === 'community' ? 0.7 : 0;
                    e.target.setStyle({ fillOpacity: opacity, weight: 0.5, color: '#1e2535' });
                },
                click: function(e) {
                    if (e.originalEvent && (e.originalEvent.ctrlKey || e.originalEvent.metaKey)) return;
                    onCommClick(cid);
                }
            });
        }
    }).addTo(map);
    commLayer.bringToBack();

    setLoading("Loading police stations...", 80);
    initPoliceStations();

    setLoading("Ready!", 100);
    setTimeout(function() {
        var ov = document.getElementById('loading-overlay');
        if (ov) ov.style.display = 'none';
    }, 400);
}

// ============================================================
// DRILL-DOWN
// ============================================================
function enterDrilldown(distId) {
    VIEW = 'community';
    var backBtn = document.getElementById('back-btn');
    if (backBtn) backBtn.style.display = 'block';

    var dData = D.dist_agg[distId];
    if (!dData) return;

    var commIds = dData.comm_ids.map(function(x){ return String(x); });

    if (map.hasLayer(distLayer)) map.removeLayer(distLayer);
    commLayer.bringToFront();

    var allScores = Object.keys(D.comm_risk).map(function(id){
        return D.comm_risk[id] ? D.comm_risk[id].score : 0;
    }).sort(function(a,b){ return a-b; });
    function qRank(s) {
        var idx = allScores.indexOf(s);
        return idx >= 0 ? idx / (allScores.length - 1 || 1) : 0;
    }

    commLayer.eachLayer(function(layer) {
        var cid = String(layer.feature.properties.area_num_1);
        if (commIds.indexOf(cid) >= 0) {
            var info = D.comm_risk[cid] || {};
            var score = info.score || 0;
            layer.setStyle({ fillColor: riskColor(qRank(score)), fillOpacity: 0.8, weight: 1, color: '#fff' });
        } else {
            layer.setStyle({ fillColor: '#1e2535', fillOpacity: 0.2, weight: 0.3, color: '#2d3f58' });
        }
    });

    var firstComm = commIds[0];
    var feat = null;
    for (var i = 0; i < C.features.length; i++) {
        var fcid = String(C.features[i].properties.area_num_1);
        if (fcid === firstComm) { feat = C.features[i]; break; }
    }
    if (feat && feat.geometry && feat.geometry.coordinates) {
        var coords = feat.geometry.coordinates[0][0];
        map.flyTo([coords[1], coords[0]], 13, { duration: 0.8 });
    }

    addCrimeDots(commIds);

    var dInfo = D.dist_risk[distId] || {};
    var statF = document.getElementById('stat-filtered');
    if (statF) statF.textContent = 'District ' + distId + ': ' + (dInfo.name || distId);

    updateCharts();
}

function exitDrilldown() {
    VIEW = 'district';
    F.district = null;
    var backBtn = document.getElementById('back-btn');
    if (backBtn) backBtn.style.display = 'none';
    var statF = document.getElementById('stat-filtered');
    if (statF) statF.textContent = 'All Chicago';

    if (!map.hasLayer(distLayer)) distLayer.addTo(map);
    commLayer.eachLayer(function(l){
        l.setStyle({ fillOpacity: 0, weight: 0.5, color: '#1e2535' });
    });
    commLayer.bringToBack();

    removeCrimeDots();
    renderDistrictFilter();
    updateCharts();
}

function addCrimeDots(commIds) {
    removeCrimeDots();
    commIds.forEach(function(cid) {
        var points = D.sample_points[cid] || [];
        points.forEach(function(p) {
            if (!p.lat || !p.lng) return;
            var m = L.circleMarker([p.lat, p.lng], {
                radius: 3, fillColor: '#e53e3e', fillOpacity: 0.7,
                color: '#9b1c1c', weight: 1
            });
            m.bindTooltip(
                '<div class="tt-title">' + (p.type||'Crime') + '</div>' +
                '<div class="tt-row"><span class="tt-lbl">Date</span><span class="tt-pct">' + (p.date||'') + '</span></div>' +
                '<div class="tt-row"><span class="tt-lbl">Location</span><span class="tt-pct">' + (p.loc||'N/A') + '</span></div>' +
                '<div class="tt-total">' + (p.desc||'') + '</div>',
                { className: 'ct-tooltip', sticky: true }
            );
            m.addTo(map);
            crimeDotMarkers.push(m);
        });
    });
}

function removeCrimeDots() {
    crimeDotMarkers.forEach(function(m){ if (map.hasLayer(m)) map.removeLayer(m); });
    crimeDotMarkers = [];
}

function onCommClick(cid) {
    if (!F.district) {
        for (var dId in D.dist_agg) {
            if (D.dist_agg[dId].comm_ids.indexOf(Number(cid)) >= 0) {
                F.district = dId;
                renderDistrictFilter();
                enterDrilldown(dId);
                return;
            }
        }
    }
}

// ============================================================
// POLICE STATIONS
// ============================================================
function initPoliceStations() {
    policeMarkers.forEach(function(m){ if (map.hasLayer(m)) map.removeLayer(m); });
    policeMarkers = [];
    var stations = window.__POLICE__;
    stations.forEach(function(p) {
        var icon = L.divIcon({
            className: 'police-icon',
            html: '<div style="background:#3182ce;border:2px solid #1a3a6e;width:10px;height:10px;border-radius:50%;"></div>'
        });
        var m = L.marker([p.lat, p.lng], { icon: icon }).bindTooltip(p.name, { permanent: false });
        policeMarkers.push(m);
    });
}

function togglePolice(show) {
    policeMarkers.forEach(function(m) {
        if (show && !map.hasLayer(m)) m.addTo(map);
        else if (!show) if (map.hasLayer(m)) map.removeLayer(m);
    });
}

function updatePoliceLines() {
    if (!userMarker) return;
    policeLines.forEach(function(l){ if (map.hasLayer(l)) map.removeLayer(l); });
    policeLines = [];
    var ulat = userMarker.getLatLng().lat;
    var ulng = userMarker.getLatLng().lng;
    var stations = window.__POLICE__;
    var sorted = stations.map(function(p) {
        return { p: p, dist: haversine(ulat, ulng, p.lat, p.lng) };
    }).sort(function(a,b){ return a.dist - b.dist; }).slice(0, 5);

    var colors = ['#48bb78','#d69e2e','#a0aec0','#718096','#4a5568'];
    sorted.forEach(function(item, i) {
        var p = item.p, dist = item.dist;
        var color = colors[i] || '#4a5568';
        var l = L.polyline([[ulat, ulng],[p.lat, p.lng]], {
            color: color, dashArray: '4,4', weight: 1.5, opacity: 0.8
        });
        l.bindTooltip(p.name + ': ' + dist.toFixed(1) + ' km', { permanent: false });
        l.addTo(map);
        policeLines.push(l);
    });
}

// ============================================================
// SEARCH
// ============================================================
function initSearch() {
    var input = document.getElementById('search-input');
    if (input) {
        input.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') searchAddress(input.value);
        });
    }

    var btn = document.getElementById('click-mode-btn');
    if (btn) {
        btn.addEventListener('click', function() {
            clickMode = !clickMode;
            btn.style.background = clickMode ? '#2d6a4f' : '#1e2535';
            btn.textContent = clickMode ? 'Clicking...' : 'Click to Place';
            if (map) map.getContainer().style.cursor = clickMode ? 'crosshair' : '';
        });
    }

    if (map) {
        map.on('click', function(e) {
            if (!clickMode) return;
            placeUserMarker(e.latlng.lat, e.latlng.lng);
            clickMode = false;
            if (btn) {
                btn.style.background = '#1e2535';
                btn.textContent = 'Click to Place';
            }
            if (map) map.getContainer().style.cursor = '';
        });
    }
}

async function searchAddress(q) {
    if (!q.trim()) return;
    try {
        var res = await fetch('https://nominatim.openstreetmap.org/search?format=json&q=' + encodeURIComponent(q + ', Chicago') + '&limit=1');
        var data = await res.json();
        if (data && data.length > 0) {
            placeUserMarker(parseFloat(data[0].lat), parseFloat(data[0].lon));
        }
    } catch(e) { console.warn('Search error', e); }
}

function placeUserMarker(lat, lng) {
    if (userMarker && map.hasLayer(userMarker)) map.removeLayer(userMarker);
    userMarker = L.marker([lat, lng], { zIndexOffset: 1000 }).addTo(map);
    userMarker.bindTooltip('Your location', { permanent: false }).openTooltip();
    updatePoliceLines();
}

// ============================================================
// MASTER UPDATE
// ============================================================
function updateAll() {
    updateCharts();
    renderCrimeTypeFilter();
    updateHeatmap();
    var totalEl = document.getElementById('stat-total');
    var filteredEl = document.getElementById('stat-filtered');
    if (totalEl && D && D.meta) totalEl.textContent = D.meta.total.toLocaleString();
    var total = D.meta ? D.meta.total : 1;
    var yrRange = (F.yearHi - F.yearLo + 1) / 25;
    var moRange = (F.monthHi - F.monthLo + 1) / 12;
    var hrRange = (F.hourHi - F.hourLo + 1) / 24;
    var pct = Math.round(yrRange * moRange * hrRange * 100);
    if (filteredEl) filteredEl.textContent = pct + '% of data' + (F.district ? ' (District ' + F.district + ')' : '');
}

function updateHeatmap() {
    if (VIEW === 'district') {
        if (!distLayer) return;
        distLayer.setStyle(function(feat) {
            var d = String(feat.properties.dist_num);
            var info = D.dist_risk[d] || {};
            return { fillColor: riskColor(info.score || 0), fillOpacity: 0.75 };
        });
    } else {
        var allScores = Object.keys(D.comm_risk).map(function(id) {
            return D.comm_risk[id] ? D.comm_risk[id].score : 0;
        }).sort(function(a,b){ return a-b; });
        function qRank(s) {
            var idx = allScores.indexOf(s);
            return idx >= 0 ? idx / (allScores.length - 1 || 1) : 0;
        }
        var dData = F.district ? D.dist_agg[F.district] : null;
        var commIds = dData ? dData.comm_ids.map(function(x){ return String(x); }) : null;
        if (!commLayer) return;
        commLayer.eachLayer(function(layer) {
            var cid = String(layer.feature.properties.area_num_1);
            var inDistrict = !commIds || commIds.indexOf(cid) >= 0;
            if (inDistrict) {
                var info = D.comm_risk[cid] || {};
                layer.setStyle({ fillColor: riskColor(qRank(info.score||0)), fillOpacity: 0.8 });
            } else {
                layer.setStyle({ fillColor: '#1e2535', fillOpacity: 0.2 });
            }
        });
    }
}

// ============================================================
// INIT
// ============================================================
function init() {
    setLoading("Loading crime data...", 10);
    try {
        D = window.__CRIME_DATA__;
        C = window.__COMM_GEO__;
        allCrimeTypes = Object.keys(D.by_type || {});
        CT_SELECTED = new Set(allCrimeTypes);
    } catch(e) {
        setLoading("Data error: " + e.message, 100);
        return;
    }

    setLoading("Setting up UI...", 40);
    renderDistrictFilter();
    renderCrimeTypeFilter();
    initSliders();
    initMap();
    initSearch();
    updateAll();
}

window.addEventListener('DOMContentLoaded', init);
"""

# --- Write HTML with all libraries embedded as data URIs ---
# (Tiles still need internet but that's expected)
HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Chicago Crime Dashboard</title>
<style>
''' + leaflet_css_src + '''
</style>
<style>
''' + '''
*{margin:0;padding:0;box-sizing:border-box}
html,body{height:100%;overflow:hidden}
body{font-family:Inter,system-ui,sans-serif;background:#0d1117;color:#e2e8f0}
#loading-overlay{position:fixed;inset:0;background:#0d1117;z-index:9999;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:16px}
.spinner{width:48px;height:48px;border:4px solid #1e2535;border-top-color:#4299e1;border-radius:50%;animation:spin .8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
#loading-bar-wrap{width:260px;height:6px;background:#1e2535;border-radius:4px;overflow:hidden}
#loading-bar{height:100%;background:linear-gradient(90deg,#4299e1,#9f7aea);border-radius:4px;width:0;transition:width .4s}
#loading-text{font-size:13px;color:#718096}
#header{height:52px;background:#131929;border-bottom:1px solid #1e2d45;display:flex;align-items:center;padding:0 18px;gap:12px;position:relative;z-index:600;flex-shrink:0}
.logo h1{font-size:16px;font-weight:700;color:#fff;white-space:nowrap}
.logo h1 span{color:#4299e1}
.header-spacer{flex:1}
.stat-chip{background:#131929;border:1px solid #1e2d45;border-radius:8px;padding:5px 12px;font-size:11px;color:#a0aec0;white-space:nowrap}
.stat-chip b{color:#4299e1}
#app{display:flex;flex-direction:column;height:calc(100vh - 52px)}
#main-view{display:flex;flex:1;overflow:hidden}
#left-col{flex:1;display:flex;flex-direction:column;overflow:hidden;min-width:0}
#map-wrap{flex:1;position:relative;min-height:0}
#map{width:100%;height:100%}
#bottom-panel{flex-shrink:0;background:#0d1117;border-top:1px solid #1e2d45}
#charts-row{display:flex;height:90px;border-bottom:1px solid #1e2d45}
.chart-card{flex:1;padding:6px 4px 2px;border-right:1px solid #1e2d45;display:flex;flex-direction:column;min-width:0}
.chart-card:last-child{border-right:none}
.chart-title{font-size:9px;font-weight:600;color:#718096;text-transform:uppercase;letter-spacing:.5px;padding:0 4px 2px;flex-shrink:0}
.chart-svg-wrap{flex:1;min-height:0;overflow:hidden}
#sliders-row{display:flex;height:52px;padding:0 2px;align-items:center}
.slider-wrap{flex:1;padding:0 8px;border-right:1px solid #1e2d45;height:100%;display:flex;flex-direction:column;justify-content:center;min-width:0}
.slider-wrap:last-child{border-right:none}
.slider-label{font-size:9px;font-weight:600;color:#4a5568;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px}
.slider-range-label{font-size:10px;color:#63b3ed;margin-bottom:4px;font-weight:500}
.range-track{position:relative;height:4px;background:#1e2535;border-radius:2px;margin:4px 8px}
.range-fill{position:absolute;top:0;height:100%;background:#4299e1;border-radius:2px}
.range-thumb{position:absolute;top:50%;transform:translate(-50%,-50%);width:14px;height:14px;background:#4299e1;border:2px solid #0d1117;border-radius:50%;cursor:pointer;z-index:2;transition:background .15s}
.range-thumb:hover,.range-thumb.active{background:#63b3ed}
#right-col{width:280px;background:#0f1621;border-left:1px solid #1e2d45;overflow-y:auto;flex-shrink:0;padding:12px 10px;display:flex;flex-direction:column;gap:12px}
.panel-section{background:#131929;border:1px solid #1e2d45;border-radius:10px;padding:12px}
.panel-section h3{font-size:11px;font-weight:600;color:#a0aec0;text-transform:uppercase;letter-spacing:.6px;margin-bottom:8px}
.crime-type-item{display:flex;align-items:center;gap:6px;padding:3px 0;cursor:pointer}
.crime-type-item input[type=checkbox]{accent-color:#4299e1;width:12px;height:12px;flex-shrink:0}
.ct-label{font-size:11px;color:#cbd5e0;min-width:0;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ct-bar-wrap{width:60px;height:6px;background:#1e2535;border-radius:3px;flex-shrink:0;overflow:hidden}
.ct-bar{height:100%;background:#48bb78;border-radius:3px;transition:width .3s}
.ct-count{font-size:10px;color:#4a5568;flex-shrink:0;min-width:36px;text-align:right}
.dist-item{padding:5px 8px;cursor:pointer;border-radius:6px;font-size:11px;color:#a0aec0;transition:all .15s;display:flex;align-items:center;gap:6px}
.dist-item:hover{background:#1e2535;color:#e2e8f0}
.dist-item.active{background:#1a2d4a;color:#4299e1;border:1px solid #2d4f7c}
.dist-badge{font-size:9px;background:#1e2535;color:#4a5568;padding:1px 5px;border-radius:4px;flex-shrink:0}
.search-row{display:flex;gap:4px;margin-bottom:8px}
#search-input{flex:1;background:#1e2535;border:1px solid #2d4f7c;color:#e2e8f0;border-radius:6px;padding:5px 8px;font-size:11px;outline:none}
#search-input:focus{border-color:#4299e1}
.click-mode-btn{background:#1e2535;border:1px solid #2d4f7c;color:#718096;border-radius:6px;padding:5px 8px;font-size:11px;cursor:pointer;white-space:nowrap}
.toggle-row{display:flex;align-items:center;justify-content:space-between}
.toggle-row label{font-size:12px;color:#a0aec0}
.toggle{position:relative;width:36px;height:20px;display:inline-block}
.toggle input{opacity:0;width:0;height:0}
.toggle-slider{position:absolute;inset:0;background:#1e2535;border-radius:20px;cursor:pointer;transition:.2s}
.toggle-slider:before{content:"";position:absolute;width:14px;height:14px;left:3px;bottom:3px;background:#4a5568;border-radius:50%;transition:.2s}
input:checked+.toggle-slider{background:#2d6a4f}
input:checked+.toggle-slider:before{transform:translateX(16px);background:#48bb78}
#map-legend{position:absolute;top:10px;left:10px;z-index:500;background:rgba(13,17,23,.9);border:1px solid #1e2d45;border-radius:10px;padding:10px 14px;backdrop-filter:blur(4px);pointer-events:none}
#map-legend h4{font-size:10px;font-weight:600;color:#a0aec0;text-transform:uppercase;letter-spacing:.6px;margin-bottom:6px}
.legend-row{display:flex;align-items:center;gap:6px;font-size:10px;color:#a0aec0;margin-bottom:3px}
.legend-swatch{width:12px;height:12px;border-radius:2px;flex-shrink:0}
#back-btn{position:absolute;top:10px;right:10px;z-index:500;background:rgba(13,17,23,.9);border:1px solid #2d4f7c;border-radius:8px;padding:6px 14px;font-size:12px;color:#4299e1;cursor:pointer;display:none;backdrop-filter:blur(4px)}
#back-btn:hover{background:#1a2d4a}
.leaflet-tooltip.ct-tooltip{background:#1a1a2e;border:1px solid #2d3f58;color:#e2e8f0;padding:8px 10px;border-radius:8px;font-size:12px;min-width:180px;box-shadow:0 4px 16px rgba(0,0,0,.5)}
.tt-title{font-weight:600;margin-bottom:6px;color:#fff;border-bottom:1px solid #2d3f58;padding-bottom:4px}
.tt-row{display:flex;align-items:center;margin:2px 0;gap:6px}
.tt-lbl{flex:1;font-size:11px;color:#a0aec0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tt-pct{font-size:10px;color:#718096;min-width:28px;text-align:right;flex-shrink:0}
.tt-total{font-size:10px;color:#4a5568;margin-top:5px;border-top:1px solid #1e2535;padding-top:4px}
</style>
</head>
<body>

<div id="loading-overlay">
  <div class="spinner"></div>
  <div id="loading-bar-wrap"><div id="loading-bar"></div></div>
  <div id="loading-text">Loading...</div>
</div>

<div id="header">
  <div class="logo"><h1>Chicago <span>Crime</span> Dashboard</h1></div>
  <div class="header-spacer"></div>
  <div class="stat-chip">Total: <b id="stat-total">—</b></div>
  <div class="stat-chip">Showing: <b id="stat-filtered">—</b></div>
</div>

<div id="app">
  <div id="main-view">
    <div id="left-col">
      <div id="map-wrap">
        <div id="map"></div>
        <div id="map-legend">
          <h4>Risk Level</h4>
          <div class="legend-row"><div class="legend-swatch" style="background:#8B0000"></div>Very High</div>
          <div class="legend-row"><div class="legend-swatch" style="background:#e53e3e"></div>High</div>
          <div class="legend-row"><div class="legend-swatch" style="background:#dd6b20"></div>Medium</div>
          <div class="legend-row"><div class="legend-swatch" style="background:#d69e2e"></div>Low</div>
          <div class="legend-row"><div class="legend-swatch" style="background:#276749"></div>Very Low</div>
        </div>
        <div id="back-btn" onclick="exitDrilldown()">&#8592; Back to Chicago</div>
      </div>

      <div id="bottom-panel">
        <div id="charts-row">
          <div class="chart-card">
            <div class="chart-title">Year</div>
            <div class="chart-svg-wrap" id="svg-year"></div>
          </div>
          <div class="chart-card">
            <div class="chart-title">Month</div>
            <div class="chart-svg-wrap" id="svg-month"></div>
          </div>
          <div class="chart-card">
            <div class="chart-title">Hour of Day</div>
            <div class="chart-svg-wrap" id="svg-hour"></div>
          </div>
        </div>
        <div id="sliders-row">
          <div class="slider-wrap">
            <div class="slider-label">Year <span class="slider-range-label" id="lbl-year"></span></div>
            <div class="range-track" id="track-year"><div class="range-fill" id="fill-year"></div><div class="range-thumb" id="thumb-year-lo"></div><div class="range-thumb" id="thumb-year-hi"></div></div>
          </div>
          <div class="slider-wrap">
            <div class="slider-label">Month <span class="slider-range-label" id="lbl-month"></span></div>
            <div class="range-track" id="track-month"><div class="range-fill" id="fill-month"></div><div class="range-thumb" id="thumb-month-lo"></div><div class="range-thumb" id="thumb-month-hi"></div></div>
          </div>
          <div class="slider-wrap">
            <div class="slider-label">Hour <span class="slider-range-label" id="lbl-hour"></span></div>
            <div class="range-track" id="track-hour"><div class="range-fill" id="fill-hour"></div><div class="range-thumb" id="thumb-hour-lo"></div><div class="range-thumb" id="thumb-hour-hi"></div></div>
          </div>
        </div>
      </div>
    </div>

    <div id="right-col">
      <div class="panel-section">
        <h3>Crime Type</h3>
        <div id="crime-type-list"></div>
      </div>

      <div class="panel-section">
        <h3>District</h3>
        <div id="district-list"></div>
      </div>

      <div class="panel-section">
        <h3>Police Stations</h3>
        <div class="search-row">
          <input id="search-input" placeholder="Search address..." type="text">
          <button id="click-mode-btn" class="click-mode-btn">Click to Place</button>
        </div>
        <div class="toggle-row">
          <label>Show Stations</label>
          <label class="toggle">
            <input type="checkbox" id="toggle-police" onchange="togglePolice(this.checked)">
            <span class="toggle-slider"></span>
          </label>
        </div>
      </div>
    </div>
  </div>
</div>

<script>
''' + leaflet_src + '''
</script>
<script>
''' + d3_src + '''
</script>
<script>
window.__CRIME_DATA__ = ''' + crime_json + ''';
window.__COMM_GEO__   = ''' + comm_json + ''';
window.__DIST_GEO__   = ''' + dist_json + ''';
window.__POLICE__     = ''' + police_json + ''';
</script>
<script>
''' + JS + '''
</script>
</body>
</html>'''

with open(os.path.join(BASE, "index.html"), "w", encoding="utf-8") as f:
    f.write(HTML)

size_mb = os.path.getsize(os.path.join(BASE, "index.html")) / 1e6
print(f"\nBuilt index.html: {size_mb:.1f} MB")
print(f"  crime_data: {len(crime_json)//1024} KB")
print(f"  comm_geo:   {len(comm_json)//1024} KB")
print(f"  dist_geo:   {len(dist_json)//1024} KB")
print(f"  JS:         {len(JS)//1024} KB")
print(f"  leaflet:    {len(leaflet_src)//1024} KB")
print(f"  d3:         {len(d3_src)//1024} KB")
print("\nDone! Open index.html in any browser.")
