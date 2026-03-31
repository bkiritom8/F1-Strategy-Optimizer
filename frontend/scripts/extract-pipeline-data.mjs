#!/usr/bin/env node
/**
 * @file scripts/extract-pipeline-data.mjs
 * @description Reads real F1 data from the F1-Strategy-Optimizer repo
 * and generates static JSON files in public/data/ for the frontend.
 *
 * Run once: node scripts/extract-pipeline-data.mjs
 *
 * Reads from:
 *   ../F1-Strategy-Optimizer/data/raw/jolpica/drivers/all.json
 *   ../F1-Strategy-Optimizer/data/raw/jolpica/circuits.json
 *   ../F1-Strategy-Optimizer/data/raw/jolpica/results/2024/*.json
 *   ../F1-Strategy-Optimizer/data/raw/jolpica/seasons.json
 *   ../F1-Strategy-Optimizer/Data-Pipeline/logs/anomaly_report.json
 *   ../F1-Strategy-Optimizer/Data-Pipeline/logs/bias_report.json
 *
 * Writes to:
 *   public/data/drivers.json
 *   public/data/circuits.json
 *   public/data/races-2024.json
 *   public/data/seasons.json
 *   public/data/pipeline-reports.json
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(__dirname, '..');
const F1_REPO = path.resolve(PROJECT_ROOT, '../F1-Strategy-Optimizer');
const OUT_DIR = path.resolve(PROJECT_ROOT, 'public/data');

// Ensure output directory exists
fs.mkdirSync(OUT_DIR, { recursive: true });

let totalFiles = 0;

// ── 1. Drivers ──────────────────────────────────────────────────────────────
try {
  const raw = JSON.parse(
    fs.readFileSync(path.join(F1_REPO, 'data/raw/jolpica/drivers/all.json'), 'utf-8')
  );
  // Keep all drivers but slim down the payload
  const drivers = raw.map((d) => ({
    id: d.driverId,
    name: `${d.givenName} ${d.familyName}`,
    code: d.code || null,
    number: d.permanentNumber || null,
    nationality: d.nationality || null,
    dob: d.dateOfBirth || null,
  }));
  fs.writeFileSync(path.join(OUT_DIR, 'drivers.json'), JSON.stringify(drivers));
  console.log(`  drivers.json: ${drivers.length} drivers`);
  totalFiles++;
} catch (e) {
  console.error('  SKIP drivers:', e.message);
}

// ── 2. Circuits ─────────────────────────────────────────────────────────────
try {
  const raw = JSON.parse(
    fs.readFileSync(path.join(F1_REPO, 'data/raw/jolpica/circuits.json'), 'utf-8')
  );
  const circuits = raw.map((c) => ({
    id: c.circuitId,
    name: c.circuitName,
    lat: parseFloat(c.Location.lat),
    lng: parseFloat(c.Location.long),
    locality: c.Location.locality,
    country: c.Location.country,
  }));
  fs.writeFileSync(path.join(OUT_DIR, 'circuits.json'), JSON.stringify(circuits));
  console.log(`  circuits.json: ${circuits.length} circuits`);
  totalFiles++;
} catch (e) {
  console.error('  SKIP circuits:', e.message);
}

// ── 3. 2024 Race Results ────────────────────────────────────────────────────
try {
  const resultsDir = path.join(F1_REPO, 'data/raw/jolpica/results/2024');
  const files = fs.readdirSync(resultsDir).filter((f) => f.endsWith('.json')).sort((a, b) => parseInt(a) - parseInt(b));
  const races = [];
  for (const file of files) {
    const race = JSON.parse(fs.readFileSync(path.join(resultsDir, file), 'utf-8'));
    if (!race || !race.Circuit) {
      console.log(`    Skipping invalid/empty race file: ${file}`);
      continue;
    }
    races.push({
      round: parseInt(race.round),
      name: race.raceName,
      date: race.date,
      circuit: {
        id: race.Circuit.circuitId,
        name: race.Circuit.circuitName,
        country: race.Circuit.Location.country,
      },
      results: race.Results.map((r) => ({
        position: parseInt(r.position),
        driver: {
          id: r.Driver.driverId,
          code: r.Driver.code,
          name: `${r.Driver.givenName} ${r.Driver.familyName}`,
        },
        constructor: r.Constructor.name,
        grid: parseInt(r.grid),
        laps: parseInt(r.laps),
        status: r.status,
        points: parseFloat(r.points),
        time: r.Time?.time || null,
        fastestLap: r.FastestLap ? {
          rank: parseInt(r.FastestLap.rank),
          lap: parseInt(r.FastestLap.lap),
          time: r.FastestLap.Time?.time || null,
        } : null,
      })),
    });
  }
  fs.writeFileSync(path.join(OUT_DIR, 'races-2024.json'), JSON.stringify(races));
  console.log(`  races-2024.json: ${races.length} races`);
  totalFiles++;
} catch (e) {
  console.error('  SKIP 2024 races:', e.message);
}

// ── 4. Seasons ──────────────────────────────────────────────────────────────
try {
  const raw = JSON.parse(
    fs.readFileSync(path.join(F1_REPO, 'data/raw/jolpica/seasons.json'), 'utf-8')
  );
  const seasons = raw.map((s) => parseInt(s.season));
  fs.writeFileSync(path.join(OUT_DIR, 'seasons.json'), JSON.stringify(seasons));
  console.log(`  seasons.json: ${seasons.length} seasons (${seasons[0]}-${seasons[seasons.length - 1]})`);
  totalFiles++;
} catch (e) {
  console.error('  SKIP seasons:', e.message);
}

// ── 5. Pipeline Reports ─────────────────────────────────────────────────────
try {
  const anomaly = JSON.parse(
    fs.readFileSync(path.join(F1_REPO, 'Data-Pipeline/logs/anomaly_report.json'), 'utf-8')
  );
  const bias = JSON.parse(
    fs.readFileSync(path.join(F1_REPO, 'Data-Pipeline/logs/bias_report.json'), 'utf-8')
  );
  fs.writeFileSync(
    path.join(OUT_DIR, 'pipeline-reports.json'),
    JSON.stringify({
      anomaly: {
        timestamp: anomaly.timestamp,
        total: anomaly.total_anomalies,
        critical: anomaly.critical,
        warnings: anomaly.warnings,
        items: anomaly.anomalies,
      },
      bias: {
        timestamp: bias.timestamp,
        totalRows: bias.total_rows,
        slices: bias.slices,
        findings: bias.findings,
      },
    })
  );
  console.log(`  pipeline-reports.json: anomalies=${anomaly.total_anomalies}, bias slices=${Object.keys(bias.slices).length}`);
  totalFiles++;
} catch (e) {
  console.error('  SKIP pipeline reports:', e.message);
}

console.log(`\nDone. ${totalFiles} files written to public/data/`);
