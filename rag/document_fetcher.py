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
import re
from langchain_core.documents import Document

logger = logging.getLogger(__name__)


def chunk_regulation_text(
    text: str,
    source_meta: dict,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> list[Document]:
    """
    Split FIA regulation text into LangChain Documents.

    If Article markers are present (e.g. "Article 28\\n..."), splits on each
    article boundary and stores the header in metadata["article"].
    Otherwise falls back to fixed-size windows with overlap, setting
    metadata["article"] = None for every chunk.

    Args:
        text: Raw regulation text.
        source_meta: Dict merged into every Document's metadata (must include
            at least "source", "doc_type", "season", "category").
        chunk_size: Characters per chunk in the fixed-window fallback.
        chunk_overlap: Overlap in characters between consecutive fixed chunks.

    Returns:
        List of Documents in original order with sequential chunk_index values.
    """
    if not text:
        return []

    article_re = re.compile(r"^(Article \d+)", re.MULTILINE)
    matches = list(article_re.finditer(text))

    if matches:
        chunks: list[Document] = []
        for i, match in enumerate(matches):
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            chunk_text = text[start:end].strip()
            if not chunk_text:
                continue
            chunks.append(
                Document(
                    page_content=chunk_text,
                    metadata={
                        **source_meta,
                        "article": match.group(1),
                        "chunk_index": len(chunks),
                    },
                )
            )
        return chunks

    # Fixed-window fallback
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append(
                Document(
                    page_content=chunk_text,
                    metadata={
                        **source_meta,
                        "article": None,
                        "chunk_index": len(chunks),
                    },
                )
            )
        if end == len(text):
            break
        start = end - chunk_overlap
    return chunks


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


# ── Historical Circuit Guides (1996–2024, not on 2025 calendar) ────────────────

_CIRCUIT_GUIDES_HISTORICAL: list[dict] = [
    {
        "name": "French Grand Prix",
        "circuit": "Circuit de Nevers Magny-Cours",
        "laps": 70,
        "length_km": 4.411,
        "drs_zones": 0,
        "season": "1991-2008",
        "content": (
            "Circuit de Nevers Magny-Cours — 70 laps, 4.411 km, no DRS (retired before 2011). "
            "Hosted French GP 1991-2008. Extremely difficult to overtake — Adelaide hairpin "
            "and the slow Nürburgring chicane provided the only real passing opportunities. "
            "Strategy was the primary differentiator; undercut dominated. "
            "Refuelling era (1994-2009): 2-3 stop fuel-heavy strategies were common. "
            "Post-refuelling (hypothetical): 1-stop MEDIUM-HARD. Low tyre degradation on "
            "smooth asphalt. Safety car probability ~25%. Pit lane time loss: ~21s. "
            "Adelaide hairpin (Turn 13) was the primary braking overtaking point. "
            "Average lap: ~1:15."
        ),
    },
    {
        "name": "German Grand Prix",
        "circuit": "Hockenheimring Baden-Württemberg",
        "laps": 67,
        "length_km": 4.574,
        "drs_zones": 2,
        "season": "1977-2019",
        "content": (
            "Hockenheimring — 67 laps, 4.574 km, 2 DRS zones (new layout from 2002). "
            "Hosted German GP alternating with Nürburgring from 2007, last race 2019. "
            "Old Hockenheim (pre-2002): three long forest straights made it one of the fastest "
            "circuits — extremely high fuel consumption, slipstreaming decisive. "
            "New Hockenheim (2002+): shortened and tightened; stadium section retained for "
            "atmosphere. 1-stop MEDIUM-HARD standard. 2-stop SOFT-MEDIUM-MEDIUM aggressive. "
            "Moderate tyre degradation. Undercut window: lap 20-25. "
            "Turn 6 hairpin (Einfahrt Motodrom) and Turn 1 are the main overtaking zones. "
            "Safety car probability ~30%. Pit lane time loss: ~21s. Average lap: ~1:13."
        ),
    },
    {
        "name": "European Grand Prix / German Grand Prix",
        "circuit": "Nürburgring Grand Prix Circuit",
        "laps": 60,
        "length_km": 5.148,
        "drs_zones": 1,
        "season": "1984-2013",
        "content": (
            "Nürburgring GP Circuit — 60 laps, 5.148 km, 1 DRS zone (from 2011). "
            "Hosted European GP and alternated as German GP through 2013. "
            "Elevation changes of 59m and Eifel mountain location create highly "
            "unpredictable weather — temperature swings of 10°C within a race are common. "
            "Intermediate tyres can be required mid-race unexpectedly. "
            "1-stop MEDIUM-HARD standard in dry; wet races become multi-stop. "
            "Safety car probability ~40% (weather and elevation). "
            "Undercut window: lap 20-28. NGK chicane (Turn 8-9) is the main overtaking zone. "
            "Michael Schumacher won here a record 5 times. "
            "Pit lane time loss: ~22s. Average lap: ~1:29 (dry)."
        ),
    },
    {
        "name": "United States Grand Prix",
        "circuit": "Indianapolis Motor Speedway",
        "laps": 73,
        "length_km": 4.192,
        "drs_zones": 0,
        "season": "2000-2007",
        "content": (
            "Indianapolis Motor Speedway — 73 laps, 4.192 km, no DRS (pre-2011 circuit). "
            "Combined infield technical section with the banked Turn 13 from the oval. "
            "2005 USGP: all 7 Michelin-shod teams withdrew after formation lap due to tyre "
            "failures on the banking — only 6 Bridgestone cars (Ferrari, Jordan, Minardi) raced. "
            "Refuelling era strategy: 2-stop standard. Banked Turn 13 created high lateral "
            "tyre loads on right-rear. Turn 1 (pit straight) and Turn 7 were overtaking zones. "
            "Safety car probability ~35%. Long pit lane — pit lane time loss: ~24s. "
            "Average lap: ~1:10."
        ),
    },
    {
        "name": "Turkish Grand Prix",
        "circuit": "Istanbul Park",
        "laps": 58,
        "length_km": 5.338,
        "drs_zones": 1,
        "season": "2005-2011, 2020-2021",
        "content": (
            "Istanbul Park — 58 laps, 5.338 km, 1 DRS zone (main straight). "
            "Hosted Turkish GP 2005-2011 and returned in 2020-2021. "
            "Turn 8: a legendary quadruple-apex high-speed left-hander sustained over ~600m — "
            "the highest lateral G-force corner on the calendar. Generates enormous rear tyre "
            "degradation — the dominant strategic challenge. "
            "1-stop MEDIUM-HARD is optimal on paper but rear deg typically forces a 2-stop. "
            "2020 Turkish GP: unique green, low-grip surface after resurfacing caused extreme "
            "sliding — some cars made 3-4 stops. "
            "Safety car probability ~25-30%. Undercut window: lap 18-22. "
            "Turn 1 is the primary overtaking zone with DRS. "
            "Pit lane time loss: ~22s. Average lap: ~1:26."
        ),
    },
    {
        "name": "Malaysian Grand Prix",
        "circuit": "Sepang International Circuit",
        "laps": 56,
        "length_km": 5.543,
        "drs_zones": 2,
        "season": "1999-2017",
        "content": (
            "Sepang International Circuit — 56 laps, 5.543 km, 2 DRS zones. "
            "Hosted Malaysian GP from 1999 to 2017. "
            "Extreme heat and humidity — air ~35°C, track ~55°C. Tropical storms "
            "are common, often arriving in the final third of the race. "
            "Weather is the single most decisive strategic variable. "
            "Dry: 1-stop MEDIUM-HARD standard. Rain: multi-stop with intermediate/wet crossovers. "
            "High tyre degradation from heat and fast low-speed corners. "
            "Safety car probability ~45%. Undercut window: lap 18-22. "
            "Turn 1 hairpin (end of long straight) and Turn 15 are the primary overtaking zones. "
            "Pit lane time loss: ~22s. Average lap: ~1:34."
        ),
    },
    {
        "name": "Korean Grand Prix",
        "circuit": "Korean International Circuit, Yeongam",
        "laps": 55,
        "length_km": 5.615,
        "drs_zones": 2,
        "season": "2010-2013",
        "content": (
            "Korean International Circuit — 55 laps, 5.615 km, 2 DRS zones. "
            "Anti-clockwise layout with a very long main straight (1.2 km) and "
            "heavily technical second half with slow corners. "
            "Extremely dusty conditions in 2010-2011 due to incomplete surrounding "
            "infrastructure — severe tyre graining on cold first laps. "
            "1-stop MEDIUM-HARD standard once track rubbered in. "
            "Undercut very effective — difficult to overtake in technical sectors. "
            "Safety car probability ~40%. Pit lane time loss: ~23s. "
            "Turn 3 hairpin (end of main straight) and Turn 12 are overtaking zones. "
            "Average lap: ~1:38."
        ),
    },
    {
        "name": "Indian Grand Prix",
        "circuit": "Buddh International Circuit, Greater Noida",
        "laps": 60,
        "length_km": 5.125,
        "drs_zones": 3,
        "season": "2011-2013",
        "content": (
            "Buddh International Circuit — 60 laps, 5.125 km, 3 DRS zones. "
            "Smooth surface with high-speed flowing first sector and three DRS zones "
            "making overtaking comparatively easier. "
            "Low tyre degradation — 1-stop MEDIUM-HARD standard. "
            "Altitude of ~198m gives mild downforce and cooling advantage. "
            "Undercut window: lap 22-28. Safety car probability ~25%. "
            "Turn 3 high-speed sweeper loads front tyres; Turn 10 hairpin is the "
            "primary braking overtaking zone. Pit lane time loss: ~21s. "
            "Average lap: ~1:27."
        ),
    },
    {
        "name": "European Grand Prix",
        "circuit": "Valencia Street Circuit",
        "laps": 57,
        "length_km": 5.419,
        "drs_zones": 2,
        "season": "2008-2012",
        "content": (
            "Valencia Street Circuit — 57 laps, 5.419 km, 2 DRS zones. "
            "Hosted European GP 2008-2012 in the port area of Valencia, Spain. "
            "One of the most difficult circuits on the calendar for on-track overtaking — "
            "wall-lined streets and 90° corners eliminated natural passing opportunities. "
            "Strategy and track position were almost entirely decisive. "
            "1-stop MEDIUM-HARD standard. Safety car probability ~50% (street nature). "
            "Long pit lane — pit lane time loss: ~24s. Undercut window: lap 18-22. "
            "Main straight DRS zone provided the only realistic overtaking opportunity. "
            "Average lap: ~1:37."
        ),
    },
    {
        "name": "Portuguese Grand Prix",
        "circuit": "Autódromo do Estoril",
        "laps": 71,
        "length_km": 4.360,
        "drs_zones": 0,
        "season": "1984-1996",
        "content": (
            "Autódromo do Estoril — 71 laps, 4.360 km, no DRS (retired before 2011). "
            "Hosted Portuguese GP until its final race in 1996. "
            "Fast flowing circuit with a long start-finish straight descending into "
            "a tight first corner. Atlantic Ocean winds created variable grip conditions. "
            "Moderate tyre degradation. Refuelling era: 2-stop strategies common. "
            "Turn 1 after the main straight was the primary overtaking point. "
            "Safety car probability ~30%. Pit lane time loss: ~21s. "
            "Average lap: ~1:22."
        ),
    },
    {
        "name": "Argentine Grand Prix",
        "circuit": "Autodromo Oscar y Juan Galvez, Buenos Aires",
        "laps": 72,
        "length_km": 4.259,
        "drs_zones": 0,
        "season": "1995-1998",
        "content": (
            "Autodromo Oscar y Juan Galvez — 72 laps, 4.259 km, no DRS (pre-2011 circuit). "
            "Hosted Argentine GP 1995-1998 in January-March (southern hemisphere summer). "
            "Bumpy, abrasive surface with summer heat driving high tyre degradation. "
            "Refuelling era: 2-stop strategies standard to manage tyre deg and heat. "
            "Safety car probability ~35%. Pit lane time loss: ~22s. "
            "Turn 1 and the Turn 6 hairpin were the primary overtaking opportunities. "
            "Average lap: ~1:28."
        ),
    },
    {
        "name": "Spanish / European Grand Prix",
        "circuit": "Circuito Permanente de Jerez",
        "laps": 69,
        "length_km": 4.428,
        "drs_zones": 0,
        "season": "1986-1997",
        "content": (
            "Circuito Permanente de Jerez — 69 laps, 4.428 km, no DRS (pre-2011 circuit). "
            "Hosted Spanish GP until 1990 and European GP in 1994 and 1997. "
            "Fast front straight with slow hairpin at Turn 1 — primary overtaking point. "
            "Low-to-medium degradation circuit. Mild October/November race conditions. "
            "Refuelling era: 2-stop strategies dominant. "
            "Famous for the 1997 European GP where Michael Schumacher collided with "
            "Jacques Villeneuve at Turn 6 — Schumacher was excluded from the championship. "
            "Safety car probability ~25%. Pit lane time loss: ~22s. Average lap: ~1:23."
        ),
    },
    {
        "name": "Sakhir Grand Prix",
        "circuit": "Bahrain Outer Circuit",
        "laps": 87,
        "length_km": 3.543,
        "drs_zones": 3,
        "season": "2020",
        "content": (
            "Bahrain Outer Circuit — 87 laps, 3.543 km, 3 DRS zones. "
            "Used only for the 2020 Sakhir Grand Prix (second Bahrain race of 2020). "
            "The outer perimeter loop with minimal slow sections — the fastest circuit "
            "variant in recent F1 history (~250 km/h average). "
            "Very short lap time (~55s) makes pit lane time loss proportionally enormous (~40% of lap). "
            "Tyre strategy: 2-stop SOFT-MEDIUM-SOFT typical due to short stint distances. "
            "George Russell (filling in for Lewis Hamilton at Mercedes) ran away with the lead "
            "before a botched pit stop and subsequent puncture ended his victory chance. "
            "Safety car probability ~40%. Pit lane time loss: ~23s relative to ~55s lap. "
            "Average lap: ~0:55."
        ),
    },
    {
        "name": "Portuguese Grand Prix (Portimão)",
        "circuit": "Autodromo Internacional do Algarve, Portimão, Portugal",
        "laps": 66,
        "length_km": 4.684,
        "drs_zones": 2,
        "season": "2020-2021",
        "content": (
            "Autodromo Internacional do Algarve — 66 laps, 4.684 km, 2 DRS zones. "
            "Hosted the Portuguese GP in 2020 and 2021 as part of the COVID-expanded calendar. "
            "The circuit's freshly resurfaced tarmac in 2020 produced extremely low grip conditions "
            "similar to Turkey 2020 — smooth asphalt offered little mechanical grip in early laps, "
            "with cars sliding and struggling to generate tyre temperature. "
            "Steep and dramatic elevation changes make braking points unique and visually spectacular — "
            "the amphitheatre section provides a natural grandstand view across multiple corners. "
            "Tyre degradation is medium-high due to surface evolution across the weekend; "
            "the standard strategy is 1-stop MEDIUM-HARD, with the undercut window opening around "
            "laps 22-28. Turn 1 and Turn 5 are the primary overtaking zones supported by DRS. "
            "Safety car probability ~30%. Pit lane time loss: ~22s. Average lap: ~1:19."
        ),
    },
    {
        "name": "Tuscan Grand Prix (Mugello — Ferrari 1000th Race)",
        "circuit": "Autodromo Internazionale del Mugello, Tuscany",
        "laps": 59,
        "length_km": 5.245,
        "drs_zones": 1,
        "season": "2020",
        "content": (
            "Autodromo Internazionale del Mugello — 59 laps, 5.245 km, 1 DRS zone on the Rettifio "
            "straight. Held only once, as the 2020 Tuscan Grand Prix — Ferrari's 1000th race. "
            "Mugello is one of the most demanding circuits in the world for both car and tyres — "
            "a continuous sequence of high-speed corners including the iconic Arrabbiata 1 and 2 "
            "complex load the rear tyres heavily, generating significant rear degradation. "
            "The SOFT compound has very limited life here; a 2-stop MEDIUM-HARD-HARD or "
            "SOFT-MEDIUM-HARD strategy was required due to very high degradation rates. "
            "The 2020 race was marred by extremely dangerous restarts — a multiple-car accident "
            "at the first restart when Grosjean braked heavily mid-pack triggered a chain reaction, "
            "sending several cars airborne; this led to a second restart and further controversy. "
            "Safety car probability is very high (~55%) based on 2020 incident history. "
            "Pit lane time loss: ~23s. Average lap: ~1:15."
        ),
    },
]


# ── Historical and Era-Specific Regulation Documents ───────────────────────────

_REGULATION_DOCS_HISTORICAL: list[dict] = [
    {
        "title": "F1 Refuelling Era Regulations 1994-2009",
        "category": "regulations_historical",
        "content": (
            "Refuelling was permitted in F1 from 1994 to 2009. "
            "Teams could add fuel during pit stops alongside tyre changes. "
            "This fundamentally changed race strategy — cars qualified with lighter fuel "
            "loads and ran harder on compounds, planning multiple fuel stops. "
            "Common strategies: 1-stop (heavy fuel load, fewer stops), "
            "2-stop (medium fuel, clean mid-race pace), 3-stop (ultra-light, maximum pace). "
            "Refuelling added ~3-5 seconds per stop above tyre change time. "
            "A full refuel from empty took ~7-9 seconds at 12 litres/second. "
            "The undercut in the refuelling era: pit early with a light fuel top-up "
            "to build speed on fresh tyres before competitor pits. "
            "Fire risk was significant — Jos Verstappen suffered a severe pit lane fire "
            "at Hockenheim 1994. Refuelling was banned from 2010 to reduce cost, danger, "
            "and improve racing spectacle. Cars now start with full fuel (up to 110 kg)."
        ),
    },
    {
        "title": "F1 Grooved Tyres Era 1998-2002",
        "category": "regulations_historical",
        "content": (
            "Grooved tyres were mandated by the FIA from 1998 to 2002 to reduce cornering speeds. "
            "Dry tyres had three longitudinal grooves cut into the contact patch (four from 1999). "
            "Grooves reduced the effective contact area, lowering maximum lateral grip by ~15-20% "
            "compared to slick tyres. "
            "Effect: slower cornering speeds to counter the aerodynamic arms race. "
            "Tyre compounds: Super Soft, Soft, Medium, Hard — Bridgestone and Michelin competing. "
            "Grooved tyres increased the importance of straight-line speed. "
            "Slick tyres were reintroduced in 2009 as part of a wider overhaul "
            "that also introduced KERS, raised minimum weight, and returned to slicks "
            "to generate more mechanical grip relative to aerodynamic grip."
        ),
    },
    {
        "title": "F1 Tyre War Era 1999-2010 (Bridgestone vs Michelin)",
        "category": "regulations_historical",
        "content": (
            "Michelin returned to F1 in 2001, challenging Bridgestone after a 1997-1998 absence. "
            "The 2001-2006 tyre war created significant strategic complexity — each supplier "
            "developed circuit-specific compounds, and cars on different tyre brands had "
            "fundamentally different race strategies and optimal tyre windows. "
            "Ferrari (Bridgestone) vs Renault/McLaren (Michelin) was the dominant rivalry. "
            "2005: One-tyre-per-race rule introduced — no tyre changes allowed in the race "
            "(except under safety car or puncture). Michelin tyres were faster but less durable. "
            "2005 USGP: Michelin tyres unsafe at Indianapolis Turn 13 banking — all 7 "
            "Michelin-shod teams withdrew after formation lap. Only 6 Bridgestone cars raced. "
            "2007-2010: Bridgestone became sole supplier, ending the tyre war. "
            "2011+: Pirelli as sole supplier with mandatory two-compound rule, "
            "levelling strategic field with identical tyre allocations per team."
        ),
    },
    {
        "title": "F1 KERS Era Regulations 2009-2013",
        "category": "regulations_historical",
        "content": (
            "KERS (Kinetic Energy Recovery System) was introduced in 2009. "
            "Harvests kinetic energy under braking, stores electrically, deploys on demand. "
            "2009 specification: 60 kW (81 hp) for up to 6.7 seconds per lap. "
            "Most teams skipped KERS in 2009 due to ~25 kg weight penalty and cooling difficulties. "
            "KERS was removed for 2010 and reintroduced for 2011 as the standard. "
            "From 2011, all competitive teams ran KERS. "
            "Strategic use: deployment timed for overtaking on straights, defending from attacks, "
            "and qualifying single lap pace. Drivers managed SoC (state of charge) throughout. "
            "Battery fitted within minimum weight — lighter drivers had more ballast flexibility. "
            "KERS was the precursor to the full MGU-K system (120 kW, 4 MJ) in the 2014 hybrid rules."
        ),
    },
    {
        "title": "F1 V10 Engine Era Regulations 1996-2005",
        "category": "regulations_historical",
        "content": (
            "V10 3.0 litre naturally aspirated engines dominated F1 from 1989 through 2005. "
            "Peak power: up to 950 bhp at 19,000 RPM (Ferrari, Renault in 2005). "
            "No engine life limits until 2004 — teams used a fresh engine for qualifying "
            "and a fresh engine for the race every weekend. "
            "2004: engines required to last two consecutive race weekends. "
            "Fuel consumption: ~75 kg per race at high-deg circuits. "
            "High-speed circuits (Monza) could average over 350 km/h on straights. "
            "V10 engine sound at 18,000+ RPM became an iconic characteristic of the era. "
            "Engine freeze and V10 ban introduced after 2005 to reduce costs and speeds. "
            "V8 customer engines replaced V10s from 2006."
        ),
    },
    {
        "title": "F1 V8 Engine Era Regulations 2006-2013",
        "category": "regulations_historical",
        "content": (
            "V8 2.4 litre naturally aspirated engines replaced V10s from 2006. "
            "Peak power: ~750 bhp at 18,000 RPM (rev limited from 2007). "
            "2007: rev limit at 19,000 RPM; 2009: reduced to 18,000 RPM. "
            "2008: traction control and electronic driver aids banned. "
            "Engine freeze introduced progressively — homologated specs with restricted development. "
            "From 2010: engine must last minimum 5 race weekends; grid penalty for exceeding allocation. "
            "Customer teams (HRT, Marussia, Caterham) ran year-old customer units. "
            "KERS reintroduced in 2011 — combined effective output ~800 bhp. "
            "DRS (Drag Reduction System) also introduced 2011. "
            "V8s replaced by 1.6 litre V6 hybrid turbo power units from 2014."
        ),
    },
    {
        "title": "F1 Hybrid V6 Turbo Era Regulations 2014-2021",
        "category": "regulations_historical",
        "content": (
            "Complete power unit overhaul in 2014: 1.6 litre V6 turbocharged engines "
            "combined with two energy recovery systems. "
            "Power unit components: ICE (internal combustion engine, ~600 bhp), "
            "TC (turbocharger), MGU-H (motor-generator unit heat — harvests exhaust energy), "
            "MGU-K (motor-generator unit kinetic — harvests braking energy, 120 kW), "
            "ES (energy store / battery), CE (control electronics). "
            "Combined peak output: ~950-1000 bhp. Mercedes dominated 2014-2021 through "
            "superior MGU-H integration — harvesting energy from turbo heat continuously. "
            "Component allocation: 3 ICE, 3 TC, 3 MGU-H, 3 MGU-K, 3 ES, 3 CE per season. "
            "Exceeding allocation triggered grid penalties (10 places per new element). "
            "MGU-H removed from 2022 regulations to reduce cost and allow new manufacturers. "
            "Fuel flow rate: 100 kg/h maximum. Maximum fuel load: 110 kg."
        ),
    },
    {
        "title": "F1 Ground Effect Era Regulations 2022+",
        "category": "regulations",
        "content": (
            "2022 introduced entirely new technical regulations centred on ground effect aerodynamics. "
            "Large venturi tunnels under the car generate downforce through suction rather "
            "than wings — cars are less sensitive to turbulent air from the car ahead. "
            "Reduced dirty air wake improved close-following and overtaking by ~35% (FIA estimate). "
            "18-inch low-profile tyres replaced 13-inch high-profile tyres. "
            "Pirelli redesigned compounds for new wheel size — C1 (hardest) to C5 (softest). "
            "Minimum weight increased to 798 kg (from ~746 kg). "
            "Budget cap enforced: $145M in 2021, reducing annually toward $135M. "
            "Sprint weekends: 6 events per year from 2023 with SQ1/SQ2/SQ3 format. "
            "Porpoising/bouncing was a significant challenge in 2022 — teams required "
            "extremely stiff suspensions for ground effect sealing, generating oscillations. "
            "TD039 (2022): FIA issued technical directive restricting porpoising on safety grounds. "
            "DRS retained but actively discussed for removal in 2026+ regulations."
        ),
    },
    {
        "title": "F1 2026 Technical and Sporting Regulations",
        "category": "regulations",
        "content": (
            "2026 marks the most comprehensive F1 regulation overhaul since 2022, "
            "covering both technical and power unit rules simultaneously. "
            "POWER UNIT: New 1.6L V6 turbo-hybrid retains ICE but removes the MGU-H entirely. "
            "Simplified hybrid system: MGU-K output increased dramatically — up to ~350 kW "
            "(from ~120 kW in 2022-2025), contributing ~50% of total power. "
            "Combined peak output: ~1000+ bhp. Fuel: fully sustainable (100% non-fossil) fuel mandatory. "
            "Maximum fuel load reduced — cars carry less fuel as electric deployment covers more distance. "
            "New manufacturers: Audi joins as a works PU supplier (replacing Sauber → Audi works team). "
            "Honda returns as a full works supplier (Red Bull/RBPT partnership). "
            "AERODYNAMICS: Active aerodynamics (manually adjustable body elements) replace DRS. "
            "Front and rear wing flaps can be adjusted by the driver via a single switch — "
            "replaces the fixed rear-wing DRS system. Both wings move simultaneously. "
            "Narrower cars: overall car width reduced from 2000 mm to 1900 mm. "
            "Shorter wheelbase mandated. Significant reduction in aerodynamic downforce "
            "(estimated ~30% less than 2025 cars) to offset increased straight-line speed "
            "from higher electric deployment. "
            "TYRES: Pirelli 18-inch wheels retained. New compound range expected — "
            "heavier MGU-K deployment changes thermal loading on tyres significantly. "
            "Teams must recalibrate tyre management strategies for the new energy profile. "
            "WEIGHT: Minimum weight target reduced (approx 768 kg) despite MGU-K enlargement, "
            "achieved by removing MGU-H and associated components. "
            "STRATEGY IMPLICATIONS: Higher electric power = more energy harvesting under braking. "
            "Shorter pit windows possible if electric overcut strategy (avoiding fuel-heavy laps) "
            "becomes viable. Active aero replaces DRS detection zones — overtaking dynamics change. "
            "Battery deployment management becomes a key within-lap tactical variable. "
            "Teams must manage both fuel (ICE) and battery (electric) separately per stint. "
            "New Concorde Agreement period: 2026-2030."
        ),
    },
    {
        "title": "F1 Parc Fermé and Setup Freeze Regulations",
        "category": "regulations",
        "content": (
            "Parc Fermé restrictions apply from the start of qualifying until race finish. "
            "Under Parc Fermé, significant car setup changes are prohibited. "
            "Permitted changes: tyre swap (like-for-like compound), repair of genuine damage "
            "with steward permission, front/rear wing within pre-declared adjustment ranges, "
            "brake duct changes for wet weather. "
            "Prohibited changes: suspension geometry, ride height, aerodynamic components, "
            "fuel load above qualifying declaration. "
            "Parc Fermé breach: if a team must break Parc Fermé to make prohibited changes "
            "(e.g. gearbox swap after qualifying crash), the car typically starts from the pit lane. "
            "Starting from pit lane removes the Q2 tyre rule — team can start on any compound. "
            "Fuel: if a car takes more fuel than declared in qualifying, it starts from pit lane. "
            "Tyre warming: blankets permitted until the 15-minute board. "
            "Car must be presented to scrutineers in Parc Fermé immediately after qualifying."
        ),
    },
    {
        "title": "F1 Budget Cap and Cost Control Regulations 2021+",
        "category": "regulations",
        "content": (
            "The F1 Financial Regulations (budget cap) were introduced from the 2021 season. "
            "Cap levels: $145M (2021), $140M (2022), $135M (2023+). "
            "Excludes: driver salaries of top 3 earners, marketing, engine development "
            "(covered by a separate Power Unit cost cap). "
            "Breach penalties: minor (≤5% over) — procedural penalty; "
            "major (>5% over) — points deduction, race ban, or exclusion from championship. "
            "2022: Red Bull found in minor breach ($2.2M over), received fine and 10% "
            "aerodynamic testing time reduction for 2023. "
            "Strategic implication: crash damage consumes cap allocation — a major crash "
            "mid-season (e.g. Zhou Guanyu's rollover at Silverstone 2022) forces teams to "
            "reduce development spend to compensate. "
            "Cap has narrowed the gap between top and midfield — competitive field from 2022+."
        ),
    },
]


# ── Extended Strategy Documents ─────────────────────────────────────────────────

_STRATEGY_DOCS: list[dict] = [
    {
        "title": "F1 Wet Weather and Intermediate Tyre Strategy",
        "category": "strategy",
        "content": (
            "Wet weather is the highest-variance strategic variable in F1. "
            "Tyre choice in changing conditions: "
            "Intermediates (green sidewall): suited for drying or lightly wet track. "
            "Disperses ~30 litres/km of water. Fastest in mixed conditions. "
            "Full wets (blue sidewall): for standing water — disperses ~85 litres/km. "
            "Slower than intermediates on a drying track. "
            "Dry-to-wet crossover: switch to inters when lap times fall 4-5s off dry pace "
            "and conditions are deteriorating. "
            "Wet-to-dry crossover: inters viable until standing water is cleared; "
            "slicks become faster when track is nearly dry and surface temperature rising. "
            "Risk: being caught on wets when Safety Car ends on a drying track "
            "— opponents switching to slicks can gain 10+ positions in 2 laps. "
            "Gamble on slicks: teams in lower positions on a nearly-dry track may gamble "
            "on slicks one lap early — if it works, gain 5-8 positions; if not, lose 5-8. "
            "Rain tyre changes carry no mandatory compound requirement — weather conditions "
            "exempt the two-compound rule."
        ),
    },
    {
        "title": "F1 ERS Deployment and Battery Management Strategy",
        "category": "strategy",
        "content": (
            "ERS management is a continuous in-race decision balancing harvesting and deployment. "
            "MGU-K maximum deployment: 120 kW (160 bhp) from battery. "
            "Maximum deployment per lap: 4 MJ (roughly 5-8 seconds of full output). "
            "Modes in use: "
            "Overtake mode — deploys full 4 MJ in a concentrated burst on the straight, "
            "typically activated by driver button. Used for attacking and defending. "
            "Harvest mode — harvests more energy under braking; builds SoC for later deployment. "
            "Balanced mode — standard race mode, charges and deploys naturally each lap. "
            "Battery state of charge (SoC) management: high SoC = ready to defend; "
            "low SoC = vulnerable to attack on next straight. "
            "DRS + ERS overtake combined gives ~20-25 km/h top-speed advantage. "
            "Circuit-specific: high-braking circuits (Monaco, Singapore) harvest more; "
            "high-speed circuits (Monza, Spa) consume more and harvest less per lap. "
            "Qualifying uses full ERS deployment every lap (no battery conservation needed). "
            "MGU-H (removed in 2022) previously harvested exhaust energy continuously — "
            "Mercedes advantage 2014-2021 was primarily MGU-H integration efficiency."
        ),
    },
    {
        "title": "F1 Qualifying Strategy and Q2 Tyre Rule Impact on Race",
        "category": "strategy",
        "content": (
            "The Q2 tyre rule forces top-10 qualifiers to start the race on their Q2 tyre. "
            "Strategic Q2 decision: "
            "SOFT Q2 time — guarantees maximum pace in Q2, best chance of top-5 grid, "
            "but forces an early pit stop (SOFT typically 10-20 laps). "
            "MEDIUM Q2 time — slower Q2 lap, possible P6-P10 grid only, but enables "
            "a longer opening stint and potentially one fewer stop overall. "
            "Teams P6-P10 regularly use MEDIUM in Q2 for the strategic advantage — "
            "a long MEDIUM first stint with HARD finish can beat 2-stop SOFT runners. "
            "Q3 tyre conservation: teams in Q3 often use one SOFT set for time and "
            "conserve remaining SOFT sets — the used Q3 set is often discarded. "
            "Starting from pit lane (Parc Fermé breach or gearbox change): removes Q2 rule, "
            "allows team to start on any compound including HARD for maximum strategic flexibility. "
            "Tyre set allocation: 13 sets total — teams must manage across all 3 days. "
            "Giving up a Q1 attempt to save a SOFT set for the race is a legitimate strategy."
        ),
    },
    {
        "title": "F1 Undercut and Overcut Timing: Quantitative Model",
        "category": "strategy",
        "content": (
            "Undercut: pit before a competitor to use tyre delta to close the gap. "
            "Undercut mechanics: "
            "1. Pitting car loses ~22s in pit lane. "
            "2. Fresh tyres provide +1.5-3.0s/lap advantage over worn tyres. "
            "3. Net: undercut closes 22s gap in approximately 8-15 laps of racing. "
            "Undercut is viable when: gap to car ahead < pit lane loss AND "
            "tyre delta per lap × remaining laps > pit lane loss. "
            "Undercut window opens: typically lap 15-20 when tyre delta first exceeds ~1.5s/lap. "
            "Overcut: stay out while competitor pits, build a gap larger than pit lane loss. "
            "Overcut viable when: worn tyre still has pace, competitor caught in traffic "
            "after stop, or VSC/SC deployment is anticipated. "
            "Circuit dependency: undercut value is highest at circuits with poor overtaking "
            "(Monaco ~60% undercut success, Monza ~25% — track position matters less there). "
            "Double undercut: both cars of a team pit together when the competitor pits, "
            "ensuring neither car loses position to the undercut. "
            "Counterplay: matching the pit stop in the same lap neutralises the undercut."
        ),
    },
    {
        "title": "F1 Defensive Strategy and Track Position Value",
        "category": "strategy",
        "content": (
            "Track position value varies significantly by circuit. "
            "High track position value (very difficult to overtake on track): "
            "Monaco, Hungaroring, Singapore, Valencia, Imola — undercut defence is critical; "
            "surrendering position in the pits is almost never recovered on track. "
            "Low track position value (easier overtaking): "
            "Monza, Spa, Baku, Bahrain — tyre advantage matters more; overcut viable. "
            "Undercut defence: react to the competitor's pit stop within the same lap. "
            "If you can pit 1 lap later than the undercut car, you likely retain position. "
            "If you react 2+ laps late, the undercut almost always succeeds. "
            "VSC defence: always pit under VSC even when leading — 5-10s time savings "
            "are nearly free. Exception: tyres younger than 5 laps with nothing to gain. "
            "Cover strategy: championship leader automatically mirrors nearest rival's pit "
            "stop regardless of own tyre state — protecting points over race result. "
            "Opposite strategy: diverging from the field with a different stop window "
            "to avoid being undercut and create a strategic advantage. "
            "DRS train escape: pit to break free of a DRS train and run in clean air — "
            "pace gain in clean air often exceeds the position lost by pitting."
        ),
    },
    {
        "title": "F1 Fuel Strategy and Lift-and-Coast Management",
        "category": "strategy",
        "content": (
            "Fuel management is a continuous race concern from the maximum starting load. "
            "Maximum starting fuel: 110 kg. Cars lighten by ~1.6-1.8 kg/lap depending on circuit. "
            "Fuel weight effect: approximately 0.033s per kg of fuel — 110 kg starting load "
            "costs ~3.6s/lap compared to the end of race. "
            "Conservation techniques: "
            "1. Lift-and-coast (LAC): lift throttle 50-100m before the normal braking point "
            "and coast briefly — saves 0.2-0.5 kg/lap. "
            "2. Engine mode reduction: lower power unit output in certain corners. "
            "3. Late apex technique: altered line reduces traction zone demands. "
            "Safety car periods provide natural fuel conservation — cars travel at ~80 km/h "
            "for multiple laps. A 5-lap SC period can save ~5 kg of fuel. "
            "Finish line minimum: teams target arriving with 1-2 kg remaining. "
            "FIA requires minimum 1 kg for post-race fuel sample — running below risks DSQ. "
            "Running out of fuel: the car is retired — no push-starts or external fuel supply permitted. "
            "Fuel delta message: engineers tell drivers the fuel delta (+ = saving, - = deficit) "
            "throughout the race to guide lift-and-coast intensity."
        ),
    },
    {
        "title": "F1 Sprint Race Strategy 2021+",
        "category": "strategy",
        "content": (
            "Sprint races were introduced in 2021 at 3 circuits, expanding to 6 per year from 2023. "
            "Sprint distance: ~100 km (approximately 30% of full race distance, 20-30 laps). "
            "Sprint grid: set by Sprint Qualifying (SQ1 12 min, SQ2 10 min, SQ3 8 min). "
            "No mandatory tyre compound rule in Sprint races. "
            "Tyre strategy: teams run SOFT for maximum sprint pace — "
            "no value in managing tyres long-term over 20-30 laps. "
            "1-stop only viable if tyre deg forces it; most sprints are no-stop. "
            "Sprint points (2023+): P1=8, P2=7, P3=6, P4=5, P5=4, P6=3, P7=2, P8=1. "
            "Sprint tyre sets are separate from main race allocation. "
            "Overtaking is aggressive — drivers take risks they would not in the main race. "
            "Main race grid is set by the standard qualifying (Q1/Q2/Q3), NOT Sprint result. "
            "Sprint damage consideration: teams limit exposure to costly incidents — "
            "marginally defending a sprint position is rarely worth a main race car repair bill. "
            "Sprint weekends: Bahrain, China, Miami, COTA, Brazil, Qatar (2024 schedule)."
        ),
    },
    {
        "title": "F1 Team Orders and Multi-Car Strategy",
        "category": "strategy",
        "content": (
            "Team orders were technically banned 2002-2010 following the Austria 2002 incident "
            "(Barrichello ordered to let Schumacher pass on final lap). Re-legalised from 2011. "
            "Common team order scenarios: "
            "1. Hold position: driver behind in championship must not attack the "
            "championship leader — protects maximum points for the team. "
            "2. Let him through: faster driver or one on better strategy let past "
            "to challenge for the lead. "
            "3. Stacked pit stops: both cars pit in sequence — first car gets priority; "
            "second car waits up to 5s. Risk: second car released into slower traffic. "
            "4. Alternate strategy: one car runs 1-stop, the other 2-stop — "
            "maximises probability at least one car benefits from different conditions. "
            "5. Swap at finish: if one driver needs a point for championship, "
            "the team may ask the leading driver to allow a swap in final laps. "
            "Multi-car strategic divergence: when one car is in clean air and another "
            "is in a DRS train, strategies diverge — DRS train car pits to escape "
            "while clean air car extends to maximise the gap."
        ),
    },
    {
        "title": "F1 Safety Car and VSC Decision Model",
        "category": "strategy",
        "content": (
            "Safety Car (SC) and Virtual Safety Car (VSC) are the highest expected-value "
            "strategic events in a race — correctly timing a stop can gain 5-15 positions. "
            "SC pit value: pit lane time loss (~22s) is largely offset by SC speed reduction. "
            "All cars travel at ~80 km/h behind SC — a pit stop costs only ~5-8s net "
            "compared to ~22s on a green lap. "
            "Decision rule — ALWAYS pit under SC unless: "
            "(a) race leader with sufficient gap to emerge in front of all traffic, OR "
            "(b) you pitted in the last 3-5 laps (tyres too fresh, no compound gain). "
            "VSC value: smaller benefit (~5-10s net depending on circuit lap time). "
            "VSC decision: pit if you were planning to pit in the next 5 laps anyway. "
            "Probabilistic SC model: circuits with high SC probability (>40%) — Monaco, Singapore, "
            "Jeddah, Baku, Melbourne — justify aggressive early pit strategies. "
            "Short first stints increase probability of catching a free SC stop before mid-race. "
            "SC timing is the single highest-variance, highest-expected-value event per race. "
            "Lapped cars: under SC, lapped cars may be directed to overtake the SC. "
            "Teams monitoring SC deployment react within 1 lap — 2 laps is usually too late."
        ),
    },
]


# ── Driver Profiles ────────────────────────────────────────────────────────────

_DRIVER_PROFILES: list[dict] = [
    # ── 2025 Grid ──────────────────────────────────────────────────────────────
    {
        "name": "Max Verstappen",
        "driver_id": "verstappen",
        "nationality": "Dutch",
        "season": 2025,
        "content": (
            "Max Verstappen (Red Bull Racing) — 4x World Drivers' Champion (2021-2024), widely "
            "regarded as the benchmark of the current era. His driving style is characterised by "
            "extremely late, aggressive braking — he exploits the trail-braking window later than "
            "almost any other driver on the grid, generating rotation and minimising apex speed loss. "
            "Under pressure, Verstappen is exceptional at managing tyre temperature without "
            "sacrificing lap time — he can nurse worn HARD tyres for 30+ laps while holding "
            "positions his rivals cannot defend. Strategy preference leans toward 1-stop when "
            "the car is fast enough, leveraging his tyre management to make long stints work. "
            "In qualifying he is the yardstick — frequently the only driver within a team's "
            "tyre simulation window on SOFT. Wet weather is another strength; his 2021 British GP "
            "and 2023 Brazilian GP wet laps are benchmark performances. "
            "Key risk: in championship-secure positions he occasionally pushes tyres too hard in "
            "the opening stint, which can compromise the second stint window."
        ),
    },
    {
        "name": "Lando Norris",
        "driver_id": "norris",
        "nationality": "British",
        "season": 2025,
        "content": (
            "Lando Norris (McLaren) — emerged as a genuine WDC contender from mid-2024, claiming "
            "his first race win at Miami 2024 and multiple victories thereafter. His driving style "
            "is smooth in the medium-to-high speed sectors where the MCL car excels, generating "
            "minimal tyre sliding and preserving rear rubber through long, sweeping corners. "
            "Norris is particularly effective in sector 2 high-speed complexes (Silverstone, "
            "Spa, Suzuka) where he extracts the most from McLaren's aerodynamic platform. "
            "Tyre management has improved significantly — he can execute long MEDIUM or HARD "
            "stints without degrading the rear-left corner. Strategy preference: aggressive "
            "undercut when McLaren's tyre warm-up advantage on SOFT allows an immediate gap "
            "after an early stop. Excellent wet-weather driver; Monaco performance was "
            "exceptional in 2024 where he secured pole. Key watchpoint: he can struggle to "
            "match Verstappen's one-lap pace on SOFT in qualifying trim, putting pressure on "
            "race strategy to compensate for grid position deficits."
        ),
    },
    {
        "name": "Charles Leclerc",
        "driver_id": "leclerc",
        "nationality": "Monégasque",
        "season": 2025,
        "content": (
            "Charles Leclerc (Ferrari) — one of the most naturally gifted qualifying drivers "
            "on the grid, with multiple poles at circuits as diverse as Monza, Spa, and Monaco. "
            "His SOFT tyre one-lap pace is exceptional; he can extract the absolute limit from "
            "Ferrari's SF-25 in Q3 when the mechanical balance is correct. In race trim, Leclerc "
            "tends to have higher degradation over long runs compared to his qualifying pace — "
            "this is partly inherent driving style (he generates heat in the rear tyres through "
            "oversteer), which makes long HARD stints a challenge. Strategy preference: aggressive "
            "SOFT start to exploit qualifying position and build a gap in the opening stint "
            "before switching to MEDIUM or HARD. Monaco is effectively Leclerc's home race — "
            "he has demonstrated exceptional pace there even before his 2024 victory. "
            "Key risk: tyre degradation on long stints under safety car restarts or extended "
            "green-flag periods in hot conditions (e.g. Bahrain, Suzuka) can compromise "
            "a 1-stop strategy."
        ),
    },
    {
        "name": "Carlos Sainz",
        "driver_id": "sainz",
        "nationality": "Spanish",
        "season": 2025,
        "content": (
            "Carlos Sainz (Williams 2025) — a consistent, technically adaptable driver who has "
            "shown the ability to perform at the front with multiple different car concepts across "
            "Ferrari, McLaren, and Williams. His tyre management is methodical — he prefers to "
            "build into a stint rather than push early, which is ideal for MEDIUM-HARD 1-stop "
            "strategies at circuits with moderate degradation. Sainz adapts his driving style "
            "to the car's balance better than most — at Williams he quickly extracted maximum "
            "performance from the FW47. Strategy preference: 1-stop MEDIUM-HARD where possible, "
            "willing to extend stints to gain track position. Strong in changing conditions — "
            "his 2023 Singapore wet-dry call was exemplary. Key strength: consistency; "
            "he rarely makes tyre-compromising errors under pressure."
        ),
    },
    {
        "name": "Lewis Hamilton",
        "driver_id": "hamilton",
        "nationality": "British",
        "season": 2025,
        "content": (
            "Lewis Hamilton (Ferrari 2025) — 7x World Drivers' Champion, the most successful "
            "driver in F1 history by race wins and championships. Hamilton moved to Ferrari for "
            "2025, partnering Charles Leclerc. His driving style is smooth and precise — "
            "exceptional tyre management that allows him to complete very long stints on MEDIUM "
            "or HARD compounds without loss of pace in the final laps. Hamilton is the benchmark "
            "wet-weather driver in the modern era, with legendary wet performances at the 2008 "
            "British GP, 2016 Brazilian GP, and 2021 British GP. Strategy preference: flexible "
            "and data-driven — he works closely with engineers and is willing to execute either "
            "undercut or overcut depending on the race situation. Strongest circuits: Silverstone, "
            "Hungary, and Spa where his smooth style maximises front-left tyre life. "
            "Key watchpoint: adapting to Ferrari's technical culture and car characteristics "
            "after 12 seasons with Mercedes."
        ),
    },
    {
        "name": "George Russell",
        "driver_id": "russell",
        "nationality": "British",
        "season": 2025,
        "content": (
            "George Russell (Mercedes) — technically precise and analytically strong, Russell "
            "brings exceptional data feedback to the team alongside his on-track pace. His "
            "driving style suits the W16's characteristic — smooth and calculated through "
            "high-speed corners, minimising rear tyre heat generation. He is particularly "
            "effective at managing MEDIUM and HARD compounds over long stints at circuits "
            "where tyre overheating is a risk. Wet weather performance is strong — his near-"
            "victory at the 2020 Sakhir GP (as a Hamilton stand-in at Mercedes) demonstrated "
            "his ability to manage an unfamiliar car at race pace. Strategy preference: "
            "undercut execution is a strength — he reliably executes the out-lap to maximise "
            "tyre warm-up quickly. Key risk: in mixed conditions his first lap on fresh SOFT "
            "tyres can be slightly cautious, reducing the undercut's full effectiveness."
        ),
    },
    {
        "name": "Fernando Alonso",
        "driver_id": "alonso",
        "nationality": "Spanish",
        "season": 2025,
        "content": (
            "Fernando Alonso (Aston Martin) — 2x World Drivers' Champion (2005-2006) and "
            "arguably the most strategically intelligent driver on the grid. Alonso routinely "
            "extracts above-car-level performance by managing tyre life beyond the expected "
            "degradation window — his ability to run 5-8 laps longer than competitors on "
            "worn compounds while still maintaining competitive pace is unmatched. In mixed "
            "or changing conditions he is outstanding — his 2012 European GP drive at Valencia "
            "from the back remains a benchmark of race-craft in traffic. Strategy preference: "
            "aggressive tyre conservation to enable 1-stop strategies at circuits where rivals "
            "are forced to 2-stop, thereby gaining track position. Defensive driving is highly "
            "skilled — he can hold positions for many laps on worn tyres. Key risk: when the "
            "AMR25 lacks qualifying pace, starting mid-field forces attrition-based strategies."
        ),
    },
    {
        "name": "Lance Stroll",
        "driver_id": "stroll",
        "nationality": "Canadian",
        "season": 2025,
        "content": (
            "Lance Stroll (Aston Martin) — a consistent mid-field driver whose performance is "
            "closely correlated with car setup quality. Stroll is notably stronger in wet or "
            "damp conditions than his dry-weather pace might suggest — his wet-weather instincts "
            "are good and he has claimed strong results when rain affects the strategic picture. "
            "His tyre management is adequate but heavily dependent on the car's setup balance; "
            "when the AMR25 is in a good window, his stints extend well. Strategy preference: "
            "safety car-driven strategies benefit Stroll most, as they compress the field and "
            "reduce the qualifying-pace disadvantage. He benefits from team pit call clarity "
            "rather than reactive strategic decisions in the heat of the moment."
        ),
    },
    {
        "name": "Sergio Perez",
        "driver_id": "perez",
        "nationality": "Mexican",
        "season": 2025,
        "content": (
            "Sergio Perez (Red Bull Racing) — a strong race-craft driver whose primary strategic "
            "asset is HARD compound tyre management. Perez can nurse the HARD tyre for "
            "40+ laps while maintaining competitive lap times, enabling 1-stop strategies at "
            "circuits where rivals cannot extend. He is effective at managing traffic in DRS "
            "trains and executing overtakes in DRS zones without relying on extreme braking "
            "aggression. Qualifying consistency has been a weakness relative to Verstappen, "
            "which frequently means starting mid-pack and relying on race pace. Strategy "
            "preference: long first stint on MEDIUM or HARD to jump rivals in the pit window, "
            "then defend to the finish on a second set of HARD tyres. Key circuit strengths: "
            "Baku, Saudi Arabia, and circuits with long high-speed straights where DRS is decisive."
        ),
    },
    {
        "name": "Oscar Piastri",
        "driver_id": "piastri",
        "nationality": "Australian",
        "season": 2025,
        "content": (
            "Oscar Piastri (McLaren) — one of the most impressive rookies-turned-race-winners "
            "in recent F1 history, claiming his first F1 victory at the 2023 Sprint in Belgium "
            "and multiple GP wins in 2024. Technically precise with quick learning curves, "
            "Piastri's data feedback and engineering communication are already at a senior level. "
            "His tyre management has improved race-by-race — he can now execute long MEDIUM "
            "stints with lap-time consistency. Strong in high-speed corners where McLaren's "
            "MCL39 is most competitive. Strategy preference: benefit from McLaren's aggressive "
            "strategy calls — early undercuts exploiting the car's SOFT warm-up advantage. "
            "Key watchpoint: back-to-back stint management under extended safety car scenarios "
            "is an area of continuing development."
        ),
    },
    {
        "name": "Nico Hülkenberg",
        "driver_id": "hulkenberg",
        "nationality": "German",
        "season": 2025,
        "content": (
            "Nico Hülkenberg (Sauber/Audi) — one of the most experienced and reliable mid-field "
            "drivers on the 2025 grid, with well over 200 race starts. His driving style is "
            "smooth and consistent — Hülkenberg rarely makes tyre-compromising errors and "
            "executes 1-stop strategies with high reliability. His race pace in a competitive "
            "car has repeatedly outperformed qualifying, making him an effective underdog "
            "strategist. Strategy preference: 1-stop MEDIUM-HARD where possible; avoids SOFT "
            "starts unless grid position mandates it. Circuit strengths include Bahrain, Spa, "
            "and Austria where his smooth cornering style minimises tyre wear. Key role at "
            "Sauber is as the experienced reference driver guiding the Audi transition."
        ),
    },
    {
        "name": "Valtteri Bottas",
        "driver_id": "bottas",
        "nationality": "Finnish",
        "season": 2025,
        "content": (
            "Valtteri Bottas (Sauber/Audi) — five-time race winner and former Mercedes driver, "
            "Bottas brings extensive strategic experience to the Sauber/Audi project. His smooth "
            "driving style minimises tyre degradation across all four compounds — he is "
            "particularly effective with MEDIUM and HARD tyres over long stints. Bottas is "
            "a proven undercut executor: his launches from pit boxes are clean and his out-laps "
            "are consistently fast, maximising the benefit of early stops. In a competitive car "
            "he can run aggressive 2-stop strategies; in a slower car he relies on consistent "
            "1-stop execution to extract maximum points from race pace. Key strength: his "
            "experience managing ERS deployment and tyre life simultaneously under race pressure."
        ),
    },
    {
        "name": "Pierre Gasly",
        "driver_id": "gasly",
        "nationality": "French",
        "season": 2025,
        "content": (
            "Pierre Gasly (Alpine) — a fast and aggressive driver who is at his best in "
            "qualifying and early-race conditions. Gasly generates strong pace on SOFT "
            "tyres — his early stint speed is one of his strategic assets, enabling the "
            "team to build a gap before rivals push. This SOFT aggression comes at a cost: "
            "tyre degradation in the second half of a stint is typically higher than average, "
            "limiting his 1-stop viability at high-deg circuits. Strategy preference: "
            "early aggressive SOFT stint to bank lap time, then manage to the flag on "
            "MEDIUM or HARD. Gasly benefits most from early safety car periods — a free "
            "stop in the first 20 laps can put him on a fresh MEDIUM or HARD for the "
            "remainder. Key circuit strengths: Monza (2020 race winner), Baku, and Hungary."
        ),
    },
    {
        "name": "Esteban Ocon",
        "driver_id": "ocon",
        "nationality": "French",
        "season": 2025,
        "content": (
            "Esteban Ocon (Haas 2025) — a consistent and composed driver who moved to Haas "
            "after his Alpine stint. Ocon's tyre management is methodical — he builds into "
            "stints gradually, avoiding early heat cycles that compromise tyre life. "
            "This makes him effective at executing 1-stop strategies and at circuits "
            "where tyre consistency over long runs wins races (Hungary, Turkey, Barcelona). "
            "His 2021 Hungarian GP win was a perfect example of alternate-strategy execution "
            "combined with strong defending. Strategy preference: alternate strategies that "
            "diverge from the main pack, using overcut windows to gain track position. "
            "Key risk: Haas tyre window dependency means performance can be erratic if "
            "the VF-25 setup is not optimised for the specific compound in use."
        ),
    },
    {
        "name": "Alexander Albon",
        "driver_id": "albon",
        "nationality": "Thai",
        "season": 2025,
        "content": (
            "Alexander Albon (Williams) — one of the most impressive mid-field performers "
            "in recent seasons, consistently outperforming the car's raw pace. Albon is "
            "exceptionally skilled at managing damaged or underperforming cars — his ability "
            "to extract consistent lap times from a Williams with tyre issues or aerodynamic "
            "damage is a key strategic asset. He is strong in overcut scenarios, using smooth "
            "tyre management to extend stints and benefit from rivals' earlier pit stops. "
            "Strategy preference: conservative MEDIUM or HARD start to enable long overcut "
            "windows; reactive to safety car timing when Williams's qualifying deficit places "
            "him mid-grid. Circuit strengths include Singapore and Monaco where car management "
            "skills outweigh raw pace."
        ),
    },
    {
        "name": "Franco Colapinto",
        "driver_id": "colapinto",
        "nationality": "Argentine",
        "season": 2025,
        "content": (
            "Franco Colapinto (Alpine 2025) — joined Alpine mid-season, replacing Jack Doohan "
            "after impressing on his 2024 Williams debut. Colapinto is an aggressive, committed "
            "driver who has raw pace on SOFT compound — his qualifying performances have "
            "outperformed car expectations on several occasions. Tyre management is still "
            "developing at F1 level; his long-run MEDIUM and HARD pace can be inconsistent "
            "as he learns degradation windows. Strategy preference: team calls tend to take "
            "a longer view since Colapinto's race management experience is building. "
            "Key strengths: bravery under braking and excellent SOFT tyre one-lap speed. "
            "Key development areas: reading tyre degradation crossover windows and adapting "
            "to variable track evolution across long stints."
        ),
    },
    {
        "name": "Oliver Bearman",
        "driver_id": "bearman",
        "nationality": "British",
        "season": 2025,
        "content": (
            "Oliver Bearman (Haas) — made a stunning F1 debut substituting for Carlos Sainz "
            "at Ferrari in Jeddah 2024, finishing 7th in his first race. Now a full-time Haas "
            "driver in 2025. Bearman's style is aggressive through braking zones with strong "
            "single-lap SOFT pace. His tyre management over race distances is developing — "
            "he has shown the ability to maintain consistent lap times once he learns "
            "the degradation window, but HARD compound management on extended stints "
            "is an area of growth. Strategy preference: the Haas team tends to exploit "
            "alternate strategies; Bearman adapts quickly to mid-race tactical changes. "
            "Key strength: composure under pressure — his 2024 debut performance in "
            "front-running traffic was exceptional for a first race."
        ),
    },
    {
        "name": "Gabriel Bortoleto",
        "driver_id": "bortoleto",
        "nationality": "Brazilian",
        "season": 2025,
        "content": (
            "Gabriel Bortoleto (Sauber/Audi) — 2024 Formula 2 champion, joined Sauber as "
            "the leading indicator of Audi's incoming driver programme. Bortoleto's F2 "
            "championship demonstrated race-craft maturity beyond his age — he managed "
            "tyre strategies and reverse-grid races with consistency. His driving style "
            "is clean and technically informed, translating well to Pirelli tyre management. "
            "Strategy preference: team strategy calls guide the approach while Bortoleto "
            "accumulates F1 data; he adapts quickly to team feedback. Key strength: "
            "qualifying pace and racecraft that punches above mid-field. "
            "Development area: extended F1 HARD compound management over 40+ lap stints."
        ),
    },
    {
        "name": "Isack Hadjar",
        "driver_id": "hadjar",
        "nationality": "French",
        "season": 2025,
        "content": (
            "Isack Hadjar (Racing Bulls) — 2024 Formula 2 runner-up, promoted to Racing Bulls "
            "for 2025. Hadjar's strength lies in high-speed corners — his car control at "
            "high-energy circuits translates well to F1 pace. His tyre strategy understanding "
            "comes from strong F2 preparation but F1 compounds offer new challenges: Pirelli "
            "C3-C5 thermal management requires precision he is still calibrating. "
            "Racing Bulls' close relationship with Red Bull provides strong data support "
            "for strategic calls, reducing the burden on Hadjar to manage all variables. "
            "Key strength: qualifying pace and overtaking aggression. "
            "Development area: MEDIUM tyre long-run management in elevated track temperatures."
        ),
    },
    {
        "name": "Kimi Antonelli",
        "driver_id": "antonelli",
        "nationality": "Italian",
        "season": 2025,
        "content": (
            "Andrea Kimi Antonelli (Mercedes) — the youngest Mercedes driver in decades, "
            "joining the team aged 18 as Lewis Hamilton's replacement. Antonelli's raw pace "
            "on SOFT compound is exceptional — his junior category performances demonstrated "
            "natural speed that placed him ahead of the curve for his age. Wet weather is "
            "a particular strength; his 2024 Formula 2 wet performances were standout. "
            "F1 tyre management is the primary development area — learning MEDIUM and HARD "
            "compound degradation windows under full race fuel loads is a multi-race "
            "calibration process. Strategy preference: team-guided calls in year one "
            "with increasing autonomy as he builds data. "
            "Key strength: natural pace on SOFT and wet tyres; key development: "
            "managing 40+ lap HARD stints without tyre temperature oscillations."
        ),
    },
    # ── Historical Legend Drivers ───────────────────────────────────────────────
    {
        "name": "Michael Schumacher",
        "driver_id": "schumacher_m",
        "nationality": "German",
        "season": "historical",
        "content": (
            "Michael Schumacher — 7x World Drivers' Champion (1994-1995, 2000-2004), "
            "the most dominant driver of the refuelling era and a master of Bridgestone "
            "tyre management. Schumacher's ability to manage Bridgestone compounds precisely "
            "gave Ferrari a measurable strategic advantage from 2000-2004 — he could push "
            "hard for 10-15 laps then switch to conservation mode seamlessly, enabling "
            "3-stop strategies that competitors could not match on Michelin. "
            "His wet weather ability was exceptional (1994 Belgian GP, 1996 Spanish GP), "
            "and his knowledge of circuit-specific braking points was unparalleled. "
            "In the refuelling era, Schumacher would often qualify on a heavy fuel load, "
            "use an underweight rival's early pace as the trigger for a pit window, "
            "then run long to the second stop on fresh tyres. "
            "He holds the record for wins at the Nürburgring (5) and Magny-Cours (8)."
        ),
    },
    {
        "name": "Ayrton Senna",
        "driver_id": "senna",
        "nationality": "Brazilian",
        "season": "historical",
        "content": (
            "Ayrton Senna — 3x World Drivers' Champion (1988, 1990, 1991), the greatest wet "
            "weather driver in F1 history by consensus. Senna's wet-weather pace created "
            "strategic problems for rivals — he could gap the field by 3-5 seconds per lap "
            "in the rain, making any tyre strategy irrelevant when he was in clear air. "
            "His qualifying pace was exceptional — 65 career poles — which gave him "
            "strategic freedom through track position. Monaco was his spiritual home: "
            "6 wins, with qualifying laps that remain benchmarks of era performance. "
            "Race strategy in the pre-refuelling era relied primarily on qualifying position "
            "and tyre compound selection; Senna's approach was aggressive SOFT starts "
            "to build maximum gap, then manage to the flag. "
            "Tyre management in dry conditions was good but his primary weapon was pace — "
            "not conservation — which occasionally led to late-race tyre compromises."
        ),
    },
    {
        "name": "Alain Prost",
        "driver_id": "prost",
        "nationality": "French",
        "season": "historical",
        "content": (
            "Alain Prost — 4x World Drivers' Champion (1985, 1986, 1989, 1993), nicknamed "
            "'The Professor' for his calculated, cerebral approach to race strategy. "
            "Prost was the pioneer of tyre-management-led strategy — he could win races "
            "while making the tyres last longer than rivals considered possible, executing "
            "what would now be called 1-stop strategies during the pre-refuelling era. "
            "His pace was measured and consistent rather than spectacular: he rarely pushed "
            "beyond 95% but sustained that 95% perfectly for a full race distance. "
            "Prost understood the energy balance of a race before telemetry provided "
            "the data — he intuitively managed fuel, tyres, and mechanical sympathy "
            "simultaneously. Strategy preference: qualify in the top 3, make the minimum "
            "number of stops, conserve resources to sprint at the end. "
            "His rivalries with Senna (1984-1989) produced many strategic masterclasses."
        ),
    },
    {
        "name": "Niki Lauda",
        "driver_id": "lauda",
        "nationality": "Austrian",
        "season": "historical",
        "content": (
            "Niki Lauda — 3x World Drivers' Champion (1975, 1977, 1984), celebrated for "
            "his cerebral, data-driven approach that was ahead of its era. Lauda was among "
            "the first drivers to systematically analyse car setup data and translate it into "
            "lap time — his technical collaboration with Ferrari and Brabham engineers was "
            "unusually deep. His 1976 season is legendary: near-fatally injured at the "
            "Nürburgring Nordschleife in August, he returned just 6 weeks later at Monza "
            "and nearly won the championship at the final race in Japan (where he withdrew "
            "in wet conditions, famously prioritising life over the title). "
            "Lauda's strategic approach was to eliminate risk through preparation — he rarely "
            "made unforced errors in race strategy. He was not the fastest qualifier but "
            "his race craft and tyre management allowed consistent front-running. "
            "His 1984 McLaren championship (over Prost by 0.5 points) was built on consistent "
            "race finishes while Prost occasionally retired."
        ),
    },
    {
        "name": "Nigel Mansell",
        "driver_id": "mansell",
        "nationality": "British",
        "season": "historical",
        "content": (
            "Nigel Mansell — 1x World Drivers' Champion (1992), one of the most aggressive "
            "and fan-favourite drivers of the 1980s-90s era. Mansell's driving style was "
            "characterised by high tyre usage — his aggressive throttle application, "
            "late braking, and commitment through high-speed corners generated significant "
            "tyre heat, leading to several famous late-race tyre failures (1986 Australian GP, "
            "1991 Canadian GP). This style made him extremely fast over short stints but "
            "created strategic vulnerability over race distances. In the refuelling era, "
            "his 1992 Williams FW14B dominance minimised these concerns by allowing "
            "shorter, more frequent stops. Key strength: raw lap time on fresh SOFT tyres; "
            "key weakness: tyre conservation on a 1-stop strategy."
        ),
    },
    {
        "name": "Kimi Räikkönen",
        "driver_id": "raikkonen",
        "nationality": "Finnish",
        "season": "historical",
        "content": (
            "Kimi Räikkönen — 1x World Drivers' Champion (2007), the 'Iceman', renowned for "
            "one of the smoothest driving styles in F1 history. Räikkönen's tyre preservation "
            "was exceptional — he could extract consistent lap times across the full life of "
            "any compound, making him ideal for 1-stop strategies. His impassive composure "
            "under pressure meant tyre management decisions were never emotionally corrupted — "
            "he conserved tyres exactly as instructed without erring in either direction. "
            "Race craft was outstanding: his 2005 Japanese GP charge from 17th to nearly "
            "winning remains one of the great late-race charge performances. "
            "Strategy preference: long stints on MEDIUM or HARD; willing to race the entire "
            "distance on minimal stops if the compound lasted. "
            "The 2007 championship was secured at the final race at Interlagos — possible "
            "only because of his consistent race management through the season."
        ),
    },
    {
        "name": "Sebastian Vettel",
        "driver_id": "vettel",
        "nationality": "German",
        "season": "historical",
        "content": (
            "Sebastian Vettel — 4x World Drivers' Champion (2010-2013), dominant in the "
            "Pirelli high-degradation era where tyre management was the central strategic "
            "differentiator. Vettel's tyre management on MEDIUM and HARD compounds was "
            "exceptional in his Red Bull years — he could complete 40+ lap stints with "
            "minimal degradation, enabling 1-stop strategies when rivals were forced "
            "to 2-stop. The 2011 championship was built on tyre-management superiority: "
            "Red Bull and Vettel combined to execute longer stints at circuits including "
            "China, Turkey, and Abu Dhabi where rival teams degraded faster. "
            "In contrast, when Pirelli shifted to harder compounds in 2013 to reduce "
            "deg concerns, Vettel and Red Bull were initially slower before adapting. "
            "Qualifying pace was extremely high — 57 career poles. "
            "Later Ferrari years (2015-2020) saw inconsistent qualifying-to-race conversion "
            "partly due to aerodynamic balance challenges."
        ),
    },
    {
        "name": "Mika Häkkinen",
        "driver_id": "hakkinen",
        "nationality": "Finnish",
        "season": "historical",
        "content": (
            "Mika Häkkinen — 2x World Drivers' Champion (1998-1999), Schumacher's closest "
            "rival in the peak Bridgestone-Michelin tyre war era. Häkkinen's driving style "
            "was smooth and metronomic — he generated excellent tyre management on "
            "Bridgestone compounds at McLaren, enabling long stints that complemented "
            "the team's 2-stop strategies in the refuelling era. "
            "His pace was extremely high in qualifying — he was one of very few drivers "
            "able to match Schumacher's single-lap Ferrari speed. Race management was "
            "calm and precise: he was patient in traffic, rarely making costly errors. "
            "The 1998 championship was particularly notable for superior tyre usage — "
            "McLaren and Bridgestone dialled in a front-limited setup that maximised "
            "consistent lap times. Strongest circuits: Spa (2 wins including the famous "
            "Schumacher-Häkkinen duel at Raidillon in 2000), Suzuka, and Silverstone."
        ),
    },
]


# ── Constructor Profiles ────────────────────────────────────────────────────────

_CONSTRUCTOR_PROFILES: list[dict] = [
    {
        "name": "Red Bull Racing",
        "constructor_id": "red_bull",
        "season": 2025,
        "content": (
            "Red Bull Racing — 6x Constructors' Champions (2010-2013, 2022-2023), the "
            "benchmark team of the ground-effect era. The RB20/RB21 is optimised for "
            "medium-speed corners where its aerodynamic platform generates the highest "
            "downforce efficiency — circuits like Bahrain, Abu Dhabi, and Hungary suit "
            "the car's characteristics. Red Bull consistently posts the fastest pit stop "
            "times on the grid: their wheel-gun + tyre-change process regularly achieves "
            "sub-2.3s stops, making aggressive undercut strategies especially potent. "
            "Tyre management on HARD compounds is a particular team strength — both "
            "Verstappen and Perez can execute very long final stints on HARD to enable "
            "1-stop strategies. Strategy approach is data-driven and aggressive: Red Bull "
            "frequently executes the undercut earlier than rivals calculate, using the "
            "advantage of clean out-laps from their pit stop speed."
        ),
    },
    {
        "name": "McLaren",
        "constructor_id": "mclaren",
        "season": 2025,
        "content": (
            "McLaren — 2024 Constructors' Champions, the team's resurgence culminating "
            "in the MCL38 and MCL39 being the fastest packages across multiple circuits. "
            "The MCL39 is strongest at high-speed circuits (Silverstone, Spa, Monza) "
            "where its aerodynamic efficiency generates high corner speeds. "
            "A distinctive strength is SOFT tyre warm-up: McLaren can activate SOFT "
            "compounds within 1-2 laps compared to rivals taking 3-4, making their "
            "undercut out-laps exceptionally quick and their qualifying low-fuel pace "
            "on fresh SOFT tyres among the best on the grid. "
            "Strategy approach: aggressive sprint strategies exploit SOFT advantage; "
            "the team is willing to 2-stop when rivals attempt 1-stop to capitalise "
            "on SOFT tyre delta. Pit stop execution is above average, consistently "
            "in the 2.4-2.7s range."
        ),
    },
    {
        "name": "Ferrari",
        "constructor_id": "ferrari",
        "season": 2025,
        "content": (
            "Ferrari — 16x Constructors' Champions with the most storied F1 history, "
            "the SF-25 showing improved race pace and qualifying performance relative "
            "to the difficult 2023 season. Ferrari's car is at its strongest in "
            "high-downforce configurations at slow-medium speed circuits (Monaco, Hungary, "
            "Singapore) where aerodynamic balance and mechanical grip are decisive. "
            "Historically, Ferrari has been vulnerable to rear tyre degradation on "
            "long runs — the SF-25 represents improvement in this area but long HARD "
            "stints can still show elevated degradation compared to Red Bull. "
            "Qualifying pace is strong — the car generates excellent peak downforce "
            "on SOFT compound. Pit stop execution is above average (2.4-2.7s range). "
            "Strategy philosophy has evolved toward more data-led aggressive calls "
            "after years of criticism for slow strategic reactions."
        ),
    },
    {
        "name": "Mercedes",
        "constructor_id": "mercedes",
        "season": 2025,
        "content": (
            "Mercedes — 8x Constructors' Champions (2014-2021), rebuilding to the front "
            "with the W16 after two difficult seasons adapting to ground effect regulations. "
            "The W16 is strongest at high-speed circuits with cool ambient conditions — "
            "Silverstone, Barcelona, and Bahrain suit its aerodynamic characteristics. "
            "Mercedes has a historical advantage in ERS integration: their MGU-K deployment "
            "optimisation provides consistent power delivery that preserves tyre life during "
            "acceleration phases. Race tyre management is strong; the team's simulation tools "
            "remain among the best in the paddock for predicting degradation crossover windows. "
            "Strategy approach is methodical and data-led — the team is excellent at multi-lap "
            "degradation modelling and will execute complex timing-game strategies. "
            "Pit stop times are consistent in the 2.5-2.8s range."
        ),
    },
    {
        "name": "Aston Martin",
        "constructor_id": "aston_martin",
        "season": 2025,
        "content": (
            "Aston Martin — AMR25 a mid-pack package with specific strengths at slow-speed "
            "and high-downforce circuits. The team's car generates good mechanical grip "
            "at circuits like Monaco, Singapore, and Hungary where chassis balance matters "
            "more than raw aerodynamic efficiency. Tyre management is a relative strength — "
            "Alonso's exceptional ability to make tyres last beyond their design window "
            "consistently extracts above-car-level race results. Strategy approach: "
            "Aston Martin frequently runs longer first stints than rivals, using "
            "tyre conservation to create overcut opportunities. Pit stop execution "
            "is mid-field consistent at 2.6-2.9s. The team benefits significantly "
            "from Alonso's strategic awareness in calls made under time pressure."
        ),
    },
    {
        "name": "Williams",
        "constructor_id": "williams",
        "season": 2025,
        "content": (
            "Williams — the FW47 shows continued improvement from the 2023-2024 "
            "rebuilding phase, with strong straight-line speed as a particular "
            "aero-efficiency characteristic. The car tends to be most competitive "
            "at power-sensitive circuits (Monza, Spa, Baku) where drag reduction "
            "strategy matters and less effective at high-downforce configurations. "
            "Tyre compound window is sensitive — Williams performs well when the "
            "compound is in its optimal temperature range but can struggle with "
            "consistency when track temperature or compound selection is off. "
            "Strategy approach: Williams frequently uses the overcut to compensate "
            "for mid-grid starting positions — extending stints while rivals pit, "
            "then coming out ahead after their own stop. Sainz's experience provides "
            "strategic maturity in executing these calls correctly."
        ),
    },
    {
        "name": "Alpine",
        "constructor_id": "alpine",
        "season": 2025,
        "content": (
            "Alpine — the A525 is a variable package that performs best at medium-"
            "downforce, technical circuits including Monaco, Hungary, and Singapore. "
            "The team has historically struggled with tyre warm-up on SOFT compound "
            "in cool conditions (e.g. Las Vegas, early-season races) but has addressed "
            "this with setup adjustments in 2025. Race pace tends to be more competitive "
            "than qualifying suggests, making alternate-strategy execution a core part "
            "of the team's points-scoring approach. Strategy approach: Alpine frequently "
            "diverges from the main pack — aggressive early SOFT stints or very late "
            "stops — to create a race within a race against mid-field rivals. "
            "Pit stop execution is mid-field at 2.6-2.9s. "
            "Team is in a transition phase as it rebuilds around Gasly and Colapinto."
        ),
    },
    {
        "name": "Haas",
        "constructor_id": "haas",
        "season": 2025,
        "content": (
            "Haas — the VF-25 is a small-budget, high-variance package whose performance "
            "is tightly correlated with tyre compound window optimisation. When Haas's "
            "setup hits the optimal tyre temperature range, the car can challenge for "
            "Q3 positions and strong midfield race results; when outside that window, "
            "performance falls away sharply. This characteristic makes strategic compound "
            "selection critically important — the team avoids SOFT compound at circuits "
            "where warm-up risk is high. Race strategy tends toward 1-stop approaches "
            "to maximise consistency. Pit stop execution has improved under current "
            "management, averaging 2.6-3.0s. Bearman and Ocon provide complementary "
            "styles — aggressive qualifying pace from Bearman, race management from Ocon."
        ),
    },
    {
        "name": "Racing Bulls",
        "constructor_id": "racing_bulls",
        "season": 2025,
        "content": (
            "Racing Bulls (formerly AlphaTauri/Toro Rosso) — the Red Bull junior team "
            "with a car closely related to Red Bull's technical framework, providing "
            "developing drivers with a competitive platform. The VCARB02 benefits from "
            "shared aerodynamic concepts, making it above-average in medium-speed "
            "corner performance relative to budget. Tyre management benefits from "
            "data inheritance — Red Bull's tyre models inform Racing Bulls' stint "
            "planning, and both Hadjar and Lawson have strong technical coaching. "
            "Strategy approach: 1-stop strategies are the default; the team executes "
            "well-timed undercuts with strong pit stop performance (2.4-2.7s). "
            "The driver development focus means strategic risks are occasionally taken "
            "to provide racing experience for the young drivers."
        ),
    },
    {
        "name": "Sauber/Audi",
        "constructor_id": "sauber",
        "season": 2025,
        "content": (
            "Sauber (transitioning to Audi works team from 2026) — the C45 is a "
            "developing midfield package as the team invests in infrastructure and "
            "personnel ahead of the full Audi branding. The car shows competitive "
            "pace at specific circuits — notably Bahrain and Spain — where its "
            "aerodynamic setup produces good corner balance. Tyre compound window "
            "is developing; the team has improved compound selection accuracy across "
            "2024-2025. Hulkenberg and Bortoleto provide a strong driver pairing "
            "with complementary qualities: Hulkenberg's experience anchors strategy "
            "execution, Bortoleto's pace develops the data set. "
            "Strategy approach: 1-stop MEDIUM-HARD is the default, with safety car "
            "timing used opportunistically. Pit stop execution is mid-field, "
            "targeting consistent 2.6-3.0s times. Long-term trajectory is "
            "upward as Audi investment flows in."
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

    Includes:
      - 24 circuit guides for the 2025 F1 calendar
      - 15 historical circuit guides (1996–2024 circuits not on 2025 calendar)
      - 11 current FIA regulation/strategy documents
      - 10 historical/era regulation documents
      - 9 extended strategy fundamentals
      - 28 driver profiles (20 x 2025 grid + 8 historical legends)
      - 10 constructor profiles (2025 grid teams)

    Arguments are kept for API compatibility with the ingestion job but are
    not used — content is hardcoded for reliability (web scraping and FIA PDF
    downloads are unreliable at ingestion time).
    """
    documents: list[Document] = []

    for guide in _CIRCUIT_GUIDES + _CIRCUIT_GUIDES_HISTORICAL:
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

    for reg in _REGULATION_DOCS + _REGULATION_DOCS_HISTORICAL + _STRATEGY_DOCS:
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

    for profile in _DRIVER_PROFILES:
        documents.append(
            Document(
                page_content=profile["content"],
                metadata={
                    "source": "driver_profile",
                    "name": profile["name"],
                    "driver_id": profile.get("driver_id", ""),
                    "nationality": profile.get("nationality", ""),
                    "season": profile["season"],
                    "category": "driver_profile",
                    "source_type": "curated",
                },
            )
        )

    for constructor in _CONSTRUCTOR_PROFILES:
        documents.append(
            Document(
                page_content=constructor["content"],
                metadata={
                    "source": "constructor_profile",
                    "name": constructor["name"],
                    "constructor_id": constructor.get("constructor_id", ""),
                    "season": constructor["season"],
                    "category": "constructor_profile",
                    "source_type": "curated",
                },
            )
        )

    n_circuits = len(_CIRCUIT_GUIDES) + len(_CIRCUIT_GUIDES_HISTORICAL)
    n_regs = (
        len(_REGULATION_DOCS) + len(_REGULATION_DOCS_HISTORICAL) + len(_STRATEGY_DOCS)
    )
    n_drivers = len(_DRIVER_PROFILES)
    n_constructors = len(_CONSTRUCTOR_PROFILES)
    logger.info(
        f"fetch_all_text_documents: {n_circuits} circuit guides + "
        f"{n_regs} regulation/strategy docs + "
        f"{n_drivers} driver profiles + "
        f"{n_constructors} constructor profiles = {len(documents)} total"
    )
    return documents
