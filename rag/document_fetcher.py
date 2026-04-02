"""
document_fetcher.py — Curated F1 text documents for RAG ingestion.

Provides two categories of Documents:
  1. Circuit guides — strategy-relevant info for all 24 circuits on the 2025 calendar
  2. FIA regulation summaries — key rules the LLM needs for strategy Q&A

Using hardcoded authoritative content rather than web scraping because:
  - FIA PDF URLs rotate with each regulation issue and return 404 within months
  - formula1.com is a JS SPA — BeautifulSoup gets placeholder text, not circuit data
  - Hardcoded content is reliable, version-controlled, and strategy-optimised
"""

import logging
from langchain_core.documents import Document

logger = logging.getLogger(__name__)


# ── Circuit Guides ─────────────────────────────────────────────────────────────

_CIRCUIT_GUIDES: list[dict] = [
    {
        "name": "Bahrain Grand Prix",
        "circuit": "Bahrain International Circuit, Sakhir",
        "laps": 57,
        "length_km": 5.412,
        "drs_zones": 3,
        "season": 2025,
        "content": (
            "The Bahrain International Circuit hosts the season opener at Sakhir. "
            "57 laps over 5.412 km. Three DRS zones on the main straight, Turn 4 "
            "exit, and Turn 12 exit. The circuit is a typical 1-stop race with "
            "MEDIUM-HARD the dominant strategy, though a 2-stop SOFT-MEDIUM-MEDIUM "
            "is viable from deep in the pack. High tyre degradation due to abrasive "
            "Sakhir asphalt — rear left is the critical tyre. Track temperatures "
            "often exceed 45°C at night. Safety car probability is moderate (~35%). "
            "Key overtaking: Turn 1 braking zone and Turn 4. Pit lane time loss: ~22s. "
            "Undercut is effective from lap 15-20. Overcut works when DRS gap is large. "
            "Fuel load at start: ~105 kg. Average lap: ~1:33."
        ),
    },
    {
        "name": "Saudi Arabian Grand Prix",
        "circuit": "Jeddah Corniche Circuit",
        "laps": 50,
        "length_km": 6.174,
        "drs_zones": 3,
        "season": 2025,
        "content": (
            "Jeddah Corniche Circuit — the fastest street circuit on the calendar. "
            "50 laps, 6.174 km. Three DRS zones. Street circuit with concrete walls "
            "means safety car probability is very high (~55%). Nearly flat-out lap "
            "with limited braking zones. Tyre deg is low — 1-stop MEDIUM-HARD is "
            "standard. Safety car timing often decides the race outcome more than "
            "pit strategy. Overcut is favoured when traffic is dense. Very limited "
            "overtaking opportunities outside of DRS zones. Pit lane time loss: ~24s. "
            "Track temp: 40-50°C. Average lap: ~1:30."
        ),
    },
    {
        "name": "Australian Grand Prix",
        "circuit": "Albert Park Circuit, Melbourne",
        "laps": 58,
        "length_km": 5.278,
        "drs_zones": 4,
        "season": 2025,
        "content": (
            "Albert Park Circuit in Melbourne. 58 laps, 5.278 km, four DRS zones. "
            "Semi-permanent street circuit with smooth surface — low tyre degradation. "
            "Standard strategy: 1-stop MEDIUM-HARD. 2-stop is viable if SC triggered "
            "mid-race. High safety car probability due to street nature (~45%). "
            "Turn 1-2 chicane is the main overtaking zone. Undercut window opens "
            "around lap 20-25. Pit lane time loss: ~22s. Track can be slippery at "
            "race start. Fuel load: ~108 kg. Average lap: ~1:20."
        ),
    },
    {
        "name": "Japanese Grand Prix",
        "circuit": "Suzuka International Racing Course",
        "laps": 53,
        "length_km": 5.807,
        "drs_zones": 1,
        "season": 2025,
        "content": (
            "Suzuka International Racing Course — 53 laps, 5.807 km, one DRS zone "
            "on the main straight. Figure-8 layout with iconic S-curves and Spoon "
            "corner. Extremely high-energy corners put heavy load on tyres — "
            "2-stop race is common. SOFT-MEDIUM-HARD or MEDIUM-MEDIUM-HARD typical. "
            "Tyre degradation is high especially on the rear right (Degner). Weather "
            "can change rapidly — wet weather probability ~30%. Overtaking is very "
            "difficult; pit strategy and undercuts are decisive. Safety car "
            "probability ~30%. Pit lane time loss: ~23s. Average lap: ~1:31."
        ),
    },
    {
        "name": "Chinese Grand Prix",
        "circuit": "Shanghai International Circuit",
        "laps": 56,
        "length_km": 5.451,
        "drs_zones": 2,
        "season": 2025,
        "content": (
            "Shanghai International Circuit — 56 laps, 5.451 km, two DRS zones. "
            "Sprint weekend. Long back straight and Turn 14 hairpin are the main "
            "overtaking zones. 1-stop MEDIUM-HARD standard, undercut is very "
            "effective from lap 18-22. High rear tyre degradation due to long "
            "high-speed corners. Safety car probability ~35%. Pit lane time loss: ~22s. "
            "Cool temperatures in April can slow tyre warm-up on SOFT compound. "
            "Average lap: ~1:33."
        ),
    },
    {
        "name": "Miami Grand Prix",
        "circuit": "Miami International Autodrome",
        "laps": 57,
        "length_km": 5.412,
        "drs_zones": 3,
        "season": 2025,
        "content": (
            "Miami International Autodrome — 57 laps, 5.412 km, three DRS zones. "
            "Sprint weekend. Street-type circuit with varying grip levels between "
            "asphalt sections. 1-stop MEDIUM-HARD dominant. SOFT start viable for "
            "aggressive early strategy. Tyre deg moderate; track evolution is "
            "significant across the weekend as rubber builds up. SC probability ~40%. "
            "Overtaking possible at Turn 1 and Turn 17. Pit lane time loss: ~23s. "
            "Track temp: 50-55°C. Average lap: ~1:28."
        ),
    },
    {
        "name": "Emilia Romagna Grand Prix",
        "circuit": "Autodromo Enzo e Dino Ferrari, Imola",
        "laps": 63,
        "length_km": 4.909,
        "drs_zones": 2,
        "season": 2025,
        "content": (
            "Imola — 63 laps, 4.909 km, two DRS zones. Very difficult to overtake "
            "on track; pit strategy is crucial. 1-stop MEDIUM-HARD is standard. "
            "SOFT start possible but must be managed carefully — graining risk on "
            "cold laps. Undulating track with kerbs that punish aggressive tyre "
            "management. Safety car probability ~35%. Undercut window: lap 25-35. "
            "Tosa and Variante Alta are key braking points. Pit lane time loss: ~23s. "
            "Average lap: ~1:15."
        ),
    },
    {
        "name": "Monaco Grand Prix",
        "circuit": "Circuit de Monaco",
        "laps": 78,
        "length_km": 3.337,
        "drs_zones": 0,
        "season": 2025,
        "content": (
            "Circuit de Monaco — 78 laps, 3.337 km, zero DRS zones. The most unique "
            "race on the calendar — overtaking on track is nearly impossible. Strategy "
            "is entirely about qualifying position and VSC/SC timing. 1-stop is "
            "standard (MEDIUM-HARD or SOFT-MEDIUM). Pit window opens as late as "
            "lap 25-30 under normal conditions. Safety car/VSC probability is very "
            "high (~65%) — reacting to SC within one lap is critical. Free pit stop "
            "under SC can promote a driver up to 3 positions. Overcut almost never "
            "works; undercut is the only play during SC. Monaco tunnel and chicane "
            "are the only real differences in pace. Pit lane time loss: ~21s. "
            "Pit entry is at the Swimming Pool section. Average lap: ~1:12."
        ),
    },
    {
        "name": "Canadian Grand Prix",
        "circuit": "Circuit Gilles Villeneuve, Montreal",
        "laps": 70,
        "length_km": 4.361,
        "drs_zones": 3,
        "season": 2025,
        "content": (
            "Circuit Gilles Villeneuve — 70 laps, 4.361 km, three DRS zones including "
            "the famous Wall of Champions straight. Street/island circuit with high "
            "safety car probability (~50%). Tyre deg is low due to smooth asphalt — "
            "1-stop MEDIUM-HARD is standard. Safety car timing is the most decisive "
            "strategic factor. Turn 1 chicane and hairpin are overtaking spots. "
            "Undercut effective if clean air available. Braking stability is critical "
            "on cold brakes after slow chicanes. Pit lane time loss: ~22s. "
            "Average lap: ~1:13."
        ),
    },
    {
        "name": "Spanish Grand Prix",
        "circuit": "Circuit de Barcelona-Catalunya",
        "laps": 66,
        "length_km": 4.657,
        "drs_zones": 2,
        "season": 2025,
        "content": (
            "Circuit de Barcelona-Catalunya — 66 laps, 4.657 km, two DRS zones. "
            "High-energy circuit demanding on all four tyres — especially rears. "
            "2-stop race is common (SOFT-MEDIUM-HARD). 1-stop MEDIUM-HARD possible "
            "but requires significant tyre management. Undercut window: lap 20-25. "
            "Turn 3 high-speed complex heavily loads the front-right. Overtaking "
            "possible at Turn 1 with DRS. Safety car probability ~25%. "
            "Pit lane time loss: ~22s. Altitude: 115m. Average lap: ~1:16."
        ),
    },
    {
        "name": "Austrian Grand Prix",
        "circuit": "Red Bull Ring, Spielberg",
        "laps": 71,
        "length_km": 4.318,
        "drs_zones": 3,
        "season": 2025,
        "content": (
            "Red Bull Ring — 71 laps, 4.318 km, three DRS zones. Short lap with "
            "big elevation changes. 1-stop MEDIUM-HARD is standard, but 2-stop "
            "SOFT-MEDIUM-MEDIUM aggressive strategy is viable. High tyre degradation "
            "due to high-speed Turn 3. Undercut window: lap 20-30. Turn 3 and Turn 4 "
            "are key overtaking spots with DRS. Safety car probability ~30%. "
            "Cool altitude conditions can affect SOFT tyre warm-up. "
            "Pit lane time loss: ~20s. Altitude: 678m. Average lap: ~1:04."
        ),
    },
    {
        "name": "British Grand Prix",
        "circuit": "Silverstone Circuit",
        "laps": 52,
        "length_km": 5.891,
        "drs_zones": 2,
        "season": 2025,
        "content": (
            "Silverstone Circuit — 52 laps, 5.891 km, two DRS zones. One of the "
            "fastest circuits, heavily loaded high-speed corners (Copse, Maggotts, "
            "Becketts, Chapel). Front-left is the critical tyre. 2-stop MEDIUM-HARD-HARD "
            "or SOFT-MEDIUM-HARD is standard; 1-stop is very difficult. Undercut "
            "is very effective from lap 15-20 due to front-left deg. Weather variable — "
            "rain probability ~25%. Safety car probability ~30%. Stowe and Village "
            "are overtaking zones. Pit lane time loss: ~23s. Average lap: ~1:27."
        ),
    },
    {
        "name": "Belgian Grand Prix",
        "circuit": "Circuit de Spa-Francorchamps",
        "laps": 44,
        "length_km": 7.004,
        "drs_zones": 2,
        "season": 2025,
        "content": (
            "Spa-Francorchamps — 44 laps, 7.004 km, two DRS zones. Sprint weekend. "
            "Longest circuit on the calendar. Weather is highly unpredictable — it "
            "can rain in one sector and be dry in another (Raidillon sector often wet). "
            "High-speed corners (Eau Rouge, Pouhon) heavily load the tyres. "
            "1-stop MEDIUM-HARD standard. 2-stop viable in unpredictable weather. "
            "Undercut window: lap 15-18. Kemmel straight is the primary overtaking zone. "
            "Safety car probability ~40% (weather-related). Pit lane time loss: ~24s. "
            "Average lap: ~1:46."
        ),
    },
    {
        "name": "Hungarian Grand Prix",
        "circuit": "Hungaroring",
        "laps": 70,
        "length_km": 4.381,
        "drs_zones": 1,
        "season": 2025,
        "content": (
            "Hungaroring — 70 laps, 4.381 km, one DRS zone. Twisty, Monaco-like "
            "circuit with very limited overtaking. Strategy is the key differentiator. "
            "1-stop MEDIUM-HARD or SOFT-HARD standard. 2-stop viable to combat "
            "overheating tyres in summer heat (track temp 55-60°C). Undercut window: "
            "lap 20-30. Turn 1 is the only real overtaking point. Safety car "
            "probability ~30%. SOFT tyre is fast here but degrades rapidly in heat. "
            "Pit lane time loss: ~21s. Average lap: ~1:17."
        ),
    },
    {
        "name": "Dutch Grand Prix",
        "circuit": "Circuit Zandvoort",
        "laps": 72,
        "length_km": 4.259,
        "drs_zones": 2,
        "season": 2025,
        "content": (
            "Circuit Zandvoort — 72 laps, 4.259 km, two DRS zones (including banked "
            "Arie Luyendyk turn). Narrow track making overtaking very difficult. "
            "Strategy is crucial — 1-stop MEDIUM-HARD standard but 2-stop is the "
            "faster option. Undercut window: lap 22-28. High rear tyre degradation "
            "due to banking loads. SOFT tyre tends to grain on first lap. "
            "Safety car probability ~35%. Slipstream effect is amplified on banking. "
            "Pit lane time loss: ~21s. Average lap: ~1:11."
        ),
    },
    {
        "name": "Italian Grand Prix",
        "circuit": "Autodromo Nazionale Monza",
        "laps": 53,
        "length_km": 5.793,
        "drs_zones": 2,
        "season": 2025,
        "content": (
            "Monza — 53 laps, 5.793 km, two DRS zones. Temple of Speed — highest "
            "average speed on the calendar (~260 km/h). Minimal downforce setup. "
            "1-stop MEDIUM-HARD standard. 2-stop possible with SOFT start. "
            "Tyre deg is low due to minimal lateral loading. Safety car probability "
            "~35%. Undercut window: lap 18-22. Variante del Rettifilo (Turn 1) and "
            "Variante Ascari are overtaking zones. Slipstreaming is critical — "
            "track position less important than tyre freshness. Pit lane time loss: ~24s. "
            "Average lap: ~1:21."
        ),
    },
    {
        "name": "Azerbaijan Grand Prix",
        "circuit": "Baku City Circuit",
        "laps": 51,
        "length_km": 6.003,
        "drs_zones": 2,
        "season": 2025,
        "content": (
            "Baku City Circuit — 51 laps, 6.003 km, two DRS zones. Street circuit "
            "with the longest straight in F1 (2.2 km). Safety car probability is "
            "very high (~55%). Tyre deg is low — 1-stop MEDIUM-HARD standard. "
            "Safety car timing is the decisive strategic variable. Race can be "
            "completely reshuffled by late SC. Turn 1 after the straight is the "
            "main overtaking zone. Narrow castle section requires car control. "
            "Undercut very effective when SC comes out. Pit lane time loss: ~22s. "
            "Average lap: ~1:43."
        ),
    },
    {
        "name": "Singapore Grand Prix",
        "circuit": "Marina Bay Street Circuit",
        "laps": 62,
        "length_km": 4.940,
        "drs_zones": 3,
        "season": 2025,
        "content": (
            "Marina Bay Street Circuit — 62 laps, 4.940 km, three DRS zones. "
            "Night race with extreme humidity (70-80%) and heat (air ~30°C, track ~35°C). "
            "Slowest street circuit — heavy braking, low-speed corners. High bumpiness "
            "leads to tyre overheating. 1-stop MEDIUM-HARD standard. Safety car "
            "probability very high (~60%). Undercut window: lap 20-25. "
            "Turn 7-8-9 complex and Turn 18 hairpin are overtaking zones. "
            "Cooling is critical — engine and brakes under maximum stress. "
            "Pit lane time loss: ~28s (long pit lane). Average lap: ~1:41."
        ),
    },
    {
        "name": "United States Grand Prix",
        "circuit": "Circuit of the Americas, Austin",
        "laps": 56,
        "length_km": 5.513,
        "drs_zones": 2,
        "season": 2025,
        "content": (
            "Circuit of the Americas (COTA) — 56 laps, 5.513 km, two DRS zones. "
            "Sprint weekend. Demanding on all tyres — big elevation change at Turn 1 "
            "creates heavy front-left loading. 1-stop MEDIUM-HARD standard; 2-stop "
            "SOFT-MEDIUM-HARD viable. Undercut window: lap 18-22. Turn 1 is the "
            "primary overtaking zone; DRS on back straight. Safety car probability ~35%. "
            "Bumps between Turns 3-6 increase tyre wear. Track temp: 45-50°C. "
            "Pit lane time loss: ~22s. Average lap: ~1:36."
        ),
    },
    {
        "name": "Mexico City Grand Prix",
        "circuit": "Autodromo Hermanos Rodriguez",
        "laps": 71,
        "length_km": 4.304,
        "drs_zones": 3,
        "season": 2025,
        "content": (
            "Autodromo Hermanos Rodriguez — 71 laps, 4.304 km, three DRS zones. "
            "High altitude (2285m) significantly reduces engine cooling efficiency "
            "and aerodynamic downforce (~25% less DF). Tyres run colder than usual — "
            "SOFT tyre lasts longer than typical. 1-stop MEDIUM-HARD standard; "
            "SOFT-MEDIUM-HARD 2-stop viable. Stadium section (Foro Sol) gives unique "
            "atmosphere. Safety car probability ~30%. Undercut window: lap 22-28. "
            "Turn 1 after the long straight is the primary overtaking zone. "
            "Pit lane time loss: ~22s. Average lap: ~1:17."
        ),
    },
    {
        "name": "São Paulo Grand Prix",
        "circuit": "Autodromo Jose Carlos Pace, Interlagos",
        "laps": 71,
        "length_km": 4.309,
        "drs_zones": 2,
        "season": 2025,
        "content": (
            "Interlagos — 71 laps, 4.309 km, two DRS zones. Sprint weekend. "
            "Anti-clockwise circuit. Weather is extremely variable — rain probability "
            "~40%, often mid-race. This can completely change strategy. High tyre "
            "deg due to surface roughness. 1-stop MEDIUM-HARD standard in dry, "
            "but many 2-stop races due to safety cars. Undercut window: lap 20-26. "
            "Turn 1 (Senna S) and Turn 4 hairpin are overtaking points. "
            "Safety car probability ~45%. Pit lane time loss: ~22s. "
            "Average lap: ~1:11."
        ),
    },
    {
        "name": "Las Vegas Grand Prix",
        "circuit": "Las Vegas Strip Circuit",
        "laps": 50,
        "length_km": 6.201,
        "drs_zones": 2,
        "season": 2025,
        "content": (
            "Las Vegas Strip Circuit — 50 laps, 6.201 km, two DRS zones. "
            "Night race with very low temperatures (~10°C ambient, ~15°C track). "
            "Cold conditions make tyre warm-up very challenging — SOFT tyre can "
            "take multiple laps to reach operating window. MEDIUM or HARD often "
            "preferred at race start. 1-stop MEDIUM-HARD standard. High-speed "
            "straight sections similar to Monza setup philosophy. Safety car "
            "probability ~40% (street circuit). Chicane on the Strip is the main "
            "overtaking zone. Pit lane time loss: ~22s. Average lap: ~1:31."
        ),
    },
    {
        "name": "Qatar Grand Prix",
        "circuit": "Lusail International Circuit",
        "laps": 57,
        "length_km": 5.380,
        "drs_zones": 2,
        "season": 2025,
        "content": (
            "Lusail International Circuit — 57 laps, 5.380 km, two DRS zones. "
            "Sprint weekend. Very smooth circuit with high-speed flowing corners. "
            "Extremely high tyre degradation — one of the most demanding circuits "
            "for rear tyres. 2-stop or even 3-stop races common. MEDIUM start "
            "recommended due to rapid SOFT deg. Undercut window: lap 15-20 "
            "(deg-driven, not strategic). Night race with temperatures 30-35°C. "
            "Safety car probability ~30%. Long run into Turn 1 is the overtaking "
            "zone. Pit lane time loss: ~22s. Average lap: ~1:24."
        ),
    },
    {
        "name": "Abu Dhabi Grand Prix",
        "circuit": "Yas Marina Circuit",
        "laps": 58,
        "length_km": 5.281,
        "drs_zones": 2,
        "season": 2025,
        "content": (
            "Yas Marina Circuit — 58 laps, 5.281 km, two DRS zones. Season finale. "
            "Twilight race (starts at sunset). Revised 2021 layout significantly "
            "improved racing quality. 1-stop MEDIUM-HARD standard; SOFT-MEDIUM "
            "2-stop viable. Moderate tyre deg. Undercut window: lap 20-25. "
            "Turn 5-6 chicane and Turn 9 are overtaking spots. Safety car "
            "probability ~30%. Track temp falls as race progresses (twilight/night). "
            "Pit lane time loss: ~22s. Average lap: ~1:25."
        ),
    },
]


# ── FIA Regulation Summaries ───────────────────────────────────────────────────

_REGULATION_DOCS: list[dict] = [
    {
        "title": "F1 Tyre Regulations 2024-2025",
        "category": "regulations",
        "content": (
            "Each team must use at least two different dry tyre compounds during a dry race. "
            "Pirelli nominates three compounds (SOFT C1-C5, MEDIUM, HARD) per event. "
            "For sprint events, there is no mandatory compound rule. "
            "Teams receive a set allocation per weekend: typically 13 sets total "
            "(8 SOFT, 3 MEDIUM, 2 HARD). After Q2, top-10 qualifiers must start on "
            "the tyre they set their fastest Q2 time on. "
            "Intermediate (GREEN) and Wet (BLUE) tyres are for wet conditions. "
            "Intermediates are the bridge tyre — used when track is drying or light rain. "
            "Full wets are for standing water conditions. "
            "Safety car periods do not exempt teams from the mandatory compound rule. "
            "Tyre blankets heat tyres to ~70°C (fronts) and ~80°C (rears) before fitting."
        ),
    },
    {
        "title": "F1 Safety Car Rules 2024-2025",
        "category": "regulations",
        "content": (
            "The Safety Car (SC) is deployed when track conditions require a significant "
            "reduction in speed. All cars must slow to SC delta speed (~80 km/h). "
            "Pit lane remains open during safety car unless a car is stranded on pit entry. "
            "Teams can pit under safety car for a free stop — the cost of pit time (~22s) "
            "is offset by the reduced delta time. "
            "Virtual Safety Car (VSC): triggered for shorter incidents. Cars must maintain "
            "a specific delta on their steering wheel (delta +/-0.1s). Pit lane is open "
            "under VSC but saving is smaller (~5-10s benefit). "
            "Safety car returns to pit after at least 1 racing lap. No overtaking until "
            "green light on SC board and SC lights go out. "
            "Final lap safety car: leader cannot overtake SC. Race ends under SC conditions "
            "in some circumstances. Lapped cars may overtake the safety car (if directed)."
        ),
    },
    {
        "title": "F1 Pit Stop Regulations 2024-2025",
        "category": "regulations",
        "content": (
            "Minimum pit stop time is enforced per event to prevent unsafe releases "
            "(typically 3.0s). Pit lane speed limit is 80 km/h (60 km/h at some venues). "
            "A driver may stop any number of times. The pit lane time loss (including "
            "speed limit sections) ranges from 19-28 seconds depending on the circuit. "
            "Teams must use at least 2 different dry compound types in a dry race. "
            "A tyre change must be performed — removing and fitting the same compound "
            "is permitted. Unsafe release from the pit box results in a 5-second "
            "time penalty or drive-through. Working on the car when it is moving "
            "in the pit lane is prohibited."
        ),
    },
    {
        "title": "F1 DRS (Drag Reduction System) Rules 2024-2025",
        "category": "regulations",
        "content": (
            "DRS (Drag Reduction System) opens the rear wing flap to reduce drag. "
            "DRS is only available in designated DRS zones detected by sensors. "
            "A driver may use DRS when within 1.0 second of the car ahead at the "
            "detection point before the DRS zone. "
            "DRS is not available in the first 2 laps of the race, first 2 laps "
            "after a safety car restart, or in wet/mixed conditions. "
            "DRS is disabled during VSC and SC periods. "
            "DRS opens the rear wing element by approximately 50mm providing "
            "10-15 km/h top speed advantage on straights. "
            "Driver must close DRS when braking for a corner. Monaco has no DRS zones."
        ),
    },
    {
        "title": "F1 Flag Rules 2024-2025",
        "category": "regulations",
        "content": (
            "GREEN FLAG: Track clear, racing resumes. "
            "YELLOW FLAG (single): Danger ahead, no overtaking, be prepared to slow. "
            "YELLOW FLAG (double): Slow down, be prepared to stop, no overtaking. "
            "RED FLAG: Race stopped. All cars must slow and return to pit lane or grid. "
            "BLUE FLAG: Shown to lapped car being approached by lead lap car — must let past within 3 blue flags. "
            "BLACK FLAG: Driver disqualified, must return to pit lane immediately. "
            "BLACK AND WHITE FLAG: Warning for unsporting behaviour. "
            "CHEQUERED FLAG: Race over. "
            "SC BOARD (orange): Safety car deployed. "
            "VSC BOARD: Virtual safety car in operation. "
            "RED AND YELLOW STRIPED FLAG: Slippery surface ahead."
        ),
    },
    {
        "title": "F1 Points System 2024-2025",
        "category": "regulations",
        "content": (
            "Race points: P1=25, P2=18, P3=15, P4=12, P5=10, P6=8, P7=6, P8=4, P9=2, P10=1. "
            "Fastest lap point: +1 point if set by driver finishing in top 10. "
            "Sprint race points: P1=8, P2=7, P3=6, P4=5, P5=4, P6=3, P7=2, P8=1. "
            "Both Drivers and Constructors Championships run simultaneously. "
            "Constructor points = sum of both drivers' points per race. "
            "DSQ removes all points from that event. "
            "In 2026, a bonus point system for fastest lap in sprint is under discussion."
        ),
    },
    {
        "title": "F1 Fuel and ERS Regulations 2024-2025",
        "category": "regulations",
        "content": (
            "Maximum fuel load at race start: 110 kg. Fuel flow rate limited to 100 kg/h. "
            "Fuel saving is critical — teams target 1.6-1.8 kg/lap depending on circuit. "
            "Energy Recovery System (ERS): harvests energy from braking (MGU-K) and "
            "exhaust heat (MGU-H removed in 2026 rules). "
            "ERS deployment: max 4 MJ per lap (120 kW peak output from MGU-K). "
            "ERS modes: Overtake mode boosts output for ~5-10s per lap. "
            "Battery state of charge (SoC) managed throughout race — too much harvesting "
            "creates drag; too little reduces deployment capability. "
            "In qualifying, full ERS deployment (Quali mode) available every lap. "
            "Fuel samples are taken post-race to verify fuel specification compliance."
        ),
    },
    {
        "title": "F1 Race Control and Penalties 2024-2025",
        "category": "regulations",
        "content": (
            "Stewards can issue: 5-second time penalty (served in pits), "
            "10-second time penalty, drive-through penalty (must complete drive-through "
            "within 3 laps of notification), stop-go penalty (10 seconds stationary), "
            "grid penalty (applied to next race), reprimand, disqualification. "
            "Penalties investigated within race or up to 2 hours post-race. "
            "Track limits: exceeding track limits consistently leads to lap time deletion "
            "or time penalty. A driver gaining an advantage by exceeding track limits "
            "may be penalised. Minimum 3 warnings before penalty for track limits. "
            "Pit lane speeding: automatic penalty based on sensor data. "
            "Collisions reviewed by stewards; at-fault driver typically receives "
            "5-second time penalty."
        ),
    },
    {
        "title": "F1 Qualifying Format 2024-2025",
        "category": "regulations",
        "content": (
            "Standard qualifying: Three segments — Q1 (18 min, bottom 5 eliminated), "
            "Q2 (15 min, bottom 5 eliminated), Q3 (12 min, top 10 shootout). "
            "Top 10 qualifiers must start on tyre used to set fastest Q2 time. "
            "Sprint weekends: Sprint Qualifying (SQ) replaces standard qualifying — "
            "SQ1/SQ2/SQ3 with same format but shorter (12/10/8 min). "
            "Sprint race (100 km / approx 30% race distance) follows with "
            "reversed grid consideration. Sprint grid based on SQ result. "
            "Main race grid determined by standard qualifying (Q1/Q2/Q3) on sprint weekends."
        ),
    },
    {
        "title": "F1 Strategy Fundamentals",
        "category": "strategy",
        "content": (
            "Undercut: Pit earlier than competitor to gain track position via fresher tyres. "
            "Works best when: tyre delta is large, pit lane time loss is small, "
            "traffic gap allows clean out-lap. "
            "Overcut: Stay out longer while competitor pits. Gain track position by "
            "building a gap that exceeds pit lane time loss. Works when: tyre is still "
            "performing, the pitting car gets stuck in traffic, SC expected. "
            "Free pit stop: Pit during Safety Car / VSC period with minimal time loss. "
            "Always take a free stop unless on ultra-hard tyres needing no change. "
            "Tyre compounds: SOFT fastest (~0.5s/lap) but degrades in 10-20 laps. "
            "MEDIUM balanced — 20-35 laps. HARD slowest but lasts 35-50+ laps. "
            "One-stop strategy: pit once, two compounds used. Quickest in low-deg races. "
            "Two-stop strategy: pit twice. Faster in high-deg races or to cover undercuts. "
            "The pit window typically opens when tyre performance drops enough that a "
            "fresh tyre set + pit lane time loss is net neutral or positive."
        ),
    },
]


# ── Public API ──────────────────────────────────────────────────────────────────

def fetch_all_text_documents(
    bucket: str = "",
    force_refresh: bool = False,
) -> list[Document]:
    """
    Return all curated F1 text documents for RAG ingestion.

    Returns circuit guides for all 24 circuits on the 2025 calendar plus
    FIA regulation summaries and strategy fundamentals.

    Arguments are kept for API compatibility with the ingestion job but are
    not used — content is hardcoded for reliability (web scraping and FIA PDF
    downloads are unreliable at ingestion time).
    """
    documents: list[Document] = []

    for guide in _CIRCUIT_GUIDES:
        documents.append(
            Document(
                page_content=guide["content"],
                metadata={
                    "source": "circuit_guide",
                    "circuit": guide["circuit"],
                    "race": guide["name"],
                    "laps": guide["laps"],
                    "length_km": guide["length_km"],
                    "drs_zones": guide["drs_zones"],
                    "season": guide["season"],
                    "category": "circuit_guide",
                    "source_type": "curated",
                },
            )
        )

    for reg in _REGULATION_DOCS:
        documents.append(
            Document(
                page_content=reg["content"],
                metadata={
                    "source": "fia_regulations",
                    "title": reg["title"],
                    "category": reg["category"],
                    "source_type": "curated",
                },
            )
        )

    logger.info(
        f"fetch_all_text_documents: {len(_CIRCUIT_GUIDES)} circuit guides + "
        f"{len(_REGULATION_DOCS)} regulation docs = {len(documents)} total"
    )
    return documents
