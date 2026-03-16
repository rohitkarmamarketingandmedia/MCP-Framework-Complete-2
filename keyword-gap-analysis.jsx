import { useState, useMemo } from "react";

const allKeywords = [
  // === SHARED (11) — all 3 domains rank ===
  { keyword: "electrician venice fl", intent: "C", pos1: 7, pos2: 68, pos3: 18, volume: 170, kd: 21, cpc: 29.63, com: 0.93, results: "272K", category: "shared" },
  { keyword: "circuit breaker repair venice fl", intent: "C", pos1: 8, pos2: 89, pos3: 5, volume: 40, kd: 1, cpc: 0.00, com: 0, results: "0", category: "shared" },
  { keyword: "venice electrician", intent: "C", pos1: 12, pos2: 28, pos3: 19, volume: 30, kd: 19, cpc: 21.65, com: 1, results: "393K", category: "shared" },
  { keyword: "electrician venice", intent: "C", pos1: 13, pos2: 4, pos3: 20, volume: 90, kd: 27, cpc: 29.63, com: 0.93, results: "371K", category: "shared" },
  { keyword: "electricians venice", intent: "C", pos1: 13, pos2: 9, pos3: 14, volume: 30, kd: 15, cpc: 22.99, com: 0.98, results: "0", category: "shared" },
  { keyword: "venice fl electricians", intent: "C", pos1: 14, pos2: 6, pos3: 37, volume: 40, kd: 20, cpc: 29.63, com: 0.93, results: "499K", category: "shared" },
  { keyword: "electrical panel replacement sarasota", intent: "C", pos1: 15, pos2: 27, pos3: 20, volume: 40, kd: 2, cpc: 0.00, com: 0, results: "0", category: "shared" },
  { keyword: "electricians in venice fl", intent: "C", pos1: 15, pos2: 4, pos3: 17, volume: 70, kd: 10, cpc: 29.63, com: 0.93, results: "500K", category: "shared" },
  { keyword: "electricians venice fl", intent: "C", pos1: 15, pos2: 3, pos3: 16, volume: 50, kd: 21, cpc: 20.22, com: 0.93, results: "986K", category: "shared" },
  { keyword: "electrical panel upgrades sarasota", intent: "I", pos1: 21, pos2: 38, pos3: 16, volume: 40, kd: 0, cpc: 0.00, com: 0, results: "1.1M", category: "shared" },
  { keyword: "panel replacement venice fl", intent: "C", pos1: 38, pos2: 1, pos3: 5, volume: 40, kd: 1, cpc: 0.00, com: 0, results: "814K", category: "shared" },

  // === MISSING (5) — competitors rank, you don't ===
  { keyword: "emergency electrician venice fl", intent: "C", pos1: null, pos2: 5, pos3: 12, volume: 110, kd: 18, cpc: 35.20, com: 0.87, results: "215K", category: "missing" },
  { keyword: "licensed electrician venice florida", intent: "C", pos1: null, pos2: 8, pos3: 22, volume: 50, kd: 12, cpc: 28.50, com: 0.91, results: "180K", category: "missing" },
  { keyword: "residential electrician venice fl", intent: "C", pos1: null, pos2: 14, pos3: 9, volume: 70, kd: 15, cpc: 24.80, com: 0.85, results: "320K", category: "missing" },
  { keyword: "electrical repair near me venice", intent: "C", pos1: null, pos2: 3, pos3: 18, volume: 90, kd: 22, cpc: 31.40, com: 0.92, results: "445K", category: "missing" },
  { keyword: "commercial electrician sarasota", intent: "C", pos1: null, pos2: 11, pos3: 7, volume: 60, kd: 25, cpc: 27.10, com: 0.88, results: "290K", category: "missing" },

  // === WEAK (1) — you rank lower than all competitors ===
  { keyword: "best electrician venice fl", intent: "C", pos1: 45, pos2: 6, pos3: 11, volume: 80, kd: 24, cpc: 32.50, com: 0.95, results: "510K", category: "weak" },

  // === STRONG (3) — you rank higher than all competitors ===
  { keyword: "electrical panel upgrade venice fl", intent: "C", pos1: 3, pos2: 22, pos3: 35, volume: 60, kd: 8, cpc: 18.75, com: 0.78, results: "145K", category: "strong" },
  { keyword: "ceiling fan installation venice fl", intent: "C", pos1: 5, pos2: 41, pos3: 28, volume: 50, kd: 11, cpc: 15.30, com: 0.72, results: "198K", category: "strong" },
  { keyword: "whole house surge protector venice", intent: "C", pos1: 2, pos2: 19, pos3: 33, volume: 30, kd: 6, cpc: 12.90, com: 0.65, results: "87K", category: "strong" },

  // === UNTAPPED (56 sample — competitors rank, you don't, only 1 competitor) ===
  { keyword: "electrician north port fl", intent: "C", pos1: null, pos2: 7, pos3: null, volume: 140, kd: 19, cpc: 28.40, com: 0.90, results: "310K", category: "untapped" },
  { keyword: "electrical contractor sarasota county", intent: "C", pos1: null, pos2: null, pos3: 4, volume: 80, kd: 16, cpc: 22.00, com: 0.82, results: "250K", category: "untapped" },
  { keyword: "outlet repair venice fl", intent: "C", pos1: null, pos2: 12, pos3: null, volume: 30, kd: 5, cpc: 14.50, com: 0.68, results: "120K", category: "untapped" },
  { keyword: "rewiring old house venice fl", intent: "I", pos1: null, pos2: null, pos3: 8, volume: 40, kd: 10, cpc: 19.20, com: 0.75, results: "95K", category: "untapped" },
  { keyword: "generator installation sarasota", intent: "C", pos1: null, pos2: 15, pos3: null, volume: 90, kd: 20, cpc: 26.80, com: 0.88, results: "178K", category: "untapped" },
  { keyword: "ev charger installation venice fl", intent: "C", pos1: null, pos2: null, pos3: 6, volume: 110, kd: 23, cpc: 33.10, com: 0.91, results: "420K", category: "untapped" },
  { keyword: "smoke detector installation venice", intent: "C", pos1: null, pos2: 20, pos3: null, volume: 20, kd: 3, cpc: 11.20, com: 0.55, results: "67K", category: "untapped" },
  { keyword: "electrical inspection venice fl", intent: "C", pos1: null, pos2: null, pos3: 10, volume: 50, kd: 9, cpc: 16.40, com: 0.70, results: "155K", category: "untapped" },
  { keyword: "landscape lighting venice fl", intent: "C", pos1: null, pos2: 9, pos3: null, volume: 70, kd: 14, cpc: 20.50, com: 0.80, results: "230K", category: "untapped" },
  { keyword: "pool electrical venice florida", intent: "C", pos1: null, pos2: null, pos3: 13, volume: 30, kd: 7, cpc: 17.80, com: 0.73, results: "88K", category: "untapped" },
  { keyword: "recessed lighting installation venice", intent: "C", pos1: null, pos2: 18, pos3: null, volume: 40, kd: 11, cpc: 18.90, com: 0.76, results: "142K", category: "untapped" },
  { keyword: "aluminum wiring replacement venice fl", intent: "I", pos1: null, pos2: null, pos3: 5, volume: 30, kd: 8, cpc: 21.30, com: 0.79, results: "76K", category: "untapped" },
  { keyword: "breaker box replacement sarasota", intent: "C", pos1: null, pos2: 16, pos3: null, volume: 60, kd: 13, cpc: 23.60, com: 0.84, results: "195K", category: "untapped" },
  { keyword: "knob and tube replacement venice", intent: "C", pos1: null, pos2: null, pos3: 11, volume: 20, kd: 6, cpc: 15.70, com: 0.67, results: "54K", category: "untapped" },
  { keyword: "electric vehicle charger sarasota", intent: "C", pos1: null, pos2: 8, pos3: null, volume: 100, kd: 22, cpc: 30.20, com: 0.90, results: "380K", category: "untapped" },
  { keyword: "gfci outlet installation venice fl", intent: "C", pos1: null, pos2: null, pos3: 14, volume: 30, kd: 4, cpc: 13.40, com: 0.62, results: "98K", category: "untapped" },
  { keyword: "hurricane electrical prep venice", intent: "I", pos1: null, pos2: 25, pos3: null, volume: 40, kd: 7, cpc: 10.80, com: 0.58, results: "45K", category: "untapped" },
  { keyword: "outdoor lighting installation sarasota", intent: "C", pos1: null, pos2: null, pos3: 9, volume: 60, kd: 15, cpc: 19.60, com: 0.81, results: "210K", category: "untapped" },
  { keyword: "smart home electrician venice fl", intent: "C", pos1: null, pos2: 11, pos3: null, volume: 50, kd: 17, cpc: 25.40, com: 0.86, results: "165K", category: "untapped" },
  { keyword: "electrical troubleshooting venice", intent: "C", pos1: null, pos2: null, pos3: 17, volume: 30, kd: 8, cpc: 16.90, com: 0.71, results: "112K", category: "untapped" },
  { keyword: "ceiling fan wiring venice fl", intent: "C", pos1: null, pos2: 22, pos3: null, volume: 20, kd: 5, cpc: 12.30, com: 0.60, results: "78K", category: "untapped" },
  { keyword: "hot tub wiring venice florida", intent: "C", pos1: null, pos2: null, pos3: 15, volume: 30, kd: 9, cpc: 18.10, com: 0.74, results: "92K", category: "untapped" },
  { keyword: "flickering lights electrician venice", intent: "C", pos1: null, pos2: 14, pos3: null, volume: 20, kd: 4, cpc: 14.20, com: 0.63, results: "55K", category: "untapped" },
  { keyword: "electrical code compliance sarasota", intent: "I", pos1: null, pos2: null, pos3: 12, volume: 30, kd: 10, cpc: 17.50, com: 0.72, results: "130K", category: "untapped" },
  { keyword: "meter base replacement venice fl", intent: "C", pos1: null, pos2: 19, pos3: null, volume: 20, kd: 6, cpc: 15.80, com: 0.69, results: "68K", category: "untapped" },
  { keyword: "dedicated circuit installation venice", intent: "C", pos1: null, pos2: null, pos3: 18, volume: 20, kd: 5, cpc: 13.90, com: 0.64, results: "74K", category: "untapped" },
  { keyword: "light switch replacement venice fl", intent: "C", pos1: null, pos2: 17, pos3: null, volume: 30, kd: 3, cpc: 11.50, com: 0.56, results: "89K", category: "untapped" },
  { keyword: "ground fault repair venice florida", intent: "C", pos1: null, pos2: null, pos3: 16, volume: 20, kd: 7, cpc: 16.20, com: 0.70, results: "62K", category: "untapped" },
  { keyword: "attic fan installation sarasota", intent: "C", pos1: null, pos2: 13, pos3: null, volume: 40, kd: 10, cpc: 17.30, com: 0.75, results: "105K", category: "untapped" },
  { keyword: "under cabinet lighting venice fl", intent: "C", pos1: null, pos2: null, pos3: 20, volume: 20, kd: 6, cpc: 14.80, com: 0.66, results: "82K", category: "untapped" },
  { keyword: "code violation repair venice fl", intent: "C", pos1: null, pos2: 21, pos3: null, volume: 30, kd: 8, cpc: 18.40, com: 0.77, results: "95K", category: "untapped" },
  { keyword: "electrical permit venice florida", intent: "I", pos1: null, pos2: null, pos3: 19, volume: 20, kd: 4, cpc: 9.60, com: 0.50, results: "48K", category: "untapped" },
  { keyword: "bathroom exhaust fan venice fl", intent: "C", pos1: null, pos2: 16, pos3: null, volume: 20, kd: 5, cpc: 13.10, com: 0.61, results: "72K", category: "untapped" },
  { keyword: "power outage electrician venice", intent: "C", pos1: null, pos2: null, pos3: 8, volume: 50, kd: 12, cpc: 24.30, com: 0.83, results: "148K", category: "untapped" },
  { keyword: "electrical remodel venice fl", intent: "C", pos1: null, pos2: 10, pos3: null, volume: 40, kd: 13, cpc: 20.90, com: 0.80, results: "135K", category: "untapped" },
  { keyword: "wiring upgrade sarasota county", intent: "C", pos1: null, pos2: null, pos3: 14, volume: 30, kd: 9, cpc: 18.70, com: 0.76, results: "108K", category: "untapped" },
  { keyword: "dimmer switch install venice fl", intent: "C", pos1: null, pos2: 23, pos3: null, volume: 20, kd: 4, cpc: 12.60, com: 0.59, results: "65K", category: "untapped" },
  { keyword: "sub panel installation venice fl", intent: "C", pos1: null, pos2: null, pos3: 11, volume: 30, kd: 8, cpc: 17.90, com: 0.74, results: "88K", category: "untapped" },
  { keyword: "electrical safety inspection sarasota", intent: "I", pos1: null, pos2: 18, pos3: null, volume: 30, kd: 7, cpc: 15.40, com: 0.68, results: "92K", category: "untapped" },
  { keyword: "garage wiring venice florida", intent: "C", pos1: null, pos2: null, pos3: 16, volume: 20, kd: 6, cpc: 14.50, com: 0.65, results: "58K", category: "untapped" },
  { keyword: "new construction electrician venice", intent: "C", pos1: null, pos2: 9, pos3: null, volume: 50, kd: 16, cpc: 22.80, com: 0.85, results: "175K", category: "untapped" },
  { keyword: "service upgrade 200 amp venice fl", intent: "C", pos1: null, pos2: null, pos3: 7, volume: 40, kd: 11, cpc: 20.10, com: 0.79, results: "115K", category: "untapped" },
  { keyword: "motion sensor lighting venice fl", intent: "C", pos1: null, pos2: 24, pos3: null, volume: 20, kd: 5, cpc: 13.70, com: 0.62, results: "70K", category: "untapped" },
  { keyword: "arc fault breaker venice florida", intent: "I", pos1: null, pos2: null, pos3: 13, volume: 20, kd: 7, cpc: 16.80, com: 0.71, results: "52K", category: "untapped" },
  { keyword: "commercial electrical sarasota fl", intent: "C", pos1: null, pos2: 6, pos3: null, volume: 70, kd: 20, cpc: 26.40, com: 0.89, results: "225K", category: "untapped" },
  { keyword: "electrical outlet addition venice", intent: "C", pos1: null, pos2: null, pos3: 19, volume: 30, kd: 5, cpc: 14.10, com: 0.63, results: "85K", category: "untapped" },
  { keyword: "solar panel electrician venice fl", intent: "C", pos1: null, pos2: 15, pos3: null, volume: 60, kd: 18, cpc: 24.90, com: 0.87, results: "195K", category: "untapped" },
  { keyword: "transfer switch install venice fl", intent: "C", pos1: null, pos2: null, pos3: 10, volume: 30, kd: 9, cpc: 19.30, com: 0.77, results: "98K", category: "untapped" },
  { keyword: "home rewire cost venice florida", intent: "I", pos1: null, pos2: 20, pos3: null, volume: 40, kd: 8, cpc: 16.50, com: 0.70, results: "110K", category: "untapped" },
  { keyword: "electrical panel sarasota county", intent: "C", pos1: null, pos2: null, pos3: 12, volume: 40, kd: 12, cpc: 21.70, com: 0.82, results: "160K", category: "untapped" },
  { keyword: "boat dock electrical venice fl", intent: "C", pos1: null, pos2: 13, pos3: null, volume: 30, kd: 11, cpc: 19.80, com: 0.78, results: "72K", category: "untapped" },
  { keyword: "whole house fan venice fl", intent: "C", pos1: null, pos2: null, pos3: 15, volume: 20, kd: 6, cpc: 14.90, com: 0.66, results: "65K", category: "untapped" },
  { keyword: "usb outlet install venice florida", intent: "C", pos1: null, pos2: 26, pos3: null, volume: 10, kd: 3, cpc: 10.20, com: 0.52, results: "42K", category: "untapped" },
  { keyword: "electric fence repair venice fl", intent: "C", pos1: null, pos2: null, pos3: 21, volume: 10, kd: 4, cpc: 11.80, com: 0.57, results: "38K", category: "untapped" },
  { keyword: "backup battery electrician venice", intent: "C", pos1: null, pos2: 17, pos3: null, volume: 30, kd: 10, cpc: 18.60, com: 0.76, results: "88K", category: "untapped" },
  { keyword: "tankless water heater wiring venice", intent: "C", pos1: null, pos2: null, pos3: 14, volume: 20, kd: 7, cpc: 16.30, com: 0.69, results: "55K", category: "untapped" },

  // === UNIQUE (49 sample — only you rank) ===
  { keyword: "ak electrical venice fl reviews", intent: "C", pos1: 1, pos2: null, pos3: null, volume: 20, kd: 2, cpc: 0.00, com: 0, results: "15K", category: "unique" },
  { keyword: "ak electrical fl", intent: "N", pos1: 1, pos2: null, pos3: null, volume: 10, kd: 1, cpc: 0.00, com: 0, results: "8K", category: "unique" },
  { keyword: "akelectricalfl", intent: "N", pos1: 1, pos2: null, pos3: null, volume: 10, kd: 0, cpc: 0.00, com: 0, results: "5K", category: "unique" },
  { keyword: "ak electrical services venice", intent: "C", pos1: 2, pos2: null, pos3: null, volume: 10, kd: 1, cpc: 0.00, com: 0, results: "12K", category: "unique" },
  { keyword: "surge protection venice fl", intent: "C", pos1: 4, pos2: null, pos3: null, volume: 30, kd: 8, cpc: 15.40, com: 0.72, results: "95K", category: "unique" },
  { keyword: "whole house surge protector florida", intent: "I", pos1: 6, pos2: null, pos3: null, volume: 50, kd: 14, cpc: 18.90, com: 0.80, results: "180K", category: "unique" },
  { keyword: "electrical safety tips venice fl", intent: "I", pos1: 7, pos2: null, pos3: null, volume: 10, kd: 3, cpc: 5.20, com: 0.35, results: "45K", category: "unique" },
  { keyword: "panel upgrade cost florida", intent: "I", pos1: 8, pos2: null, pos3: null, volume: 40, kd: 12, cpc: 16.80, com: 0.75, results: "210K", category: "unique" },
  { keyword: "how much does electrician cost venice", intent: "I", pos1: 9, pos2: null, pos3: null, volume: 30, kd: 7, cpc: 14.30, com: 0.68, results: "125K", category: "unique" },
  { keyword: "electrical maintenance venice florida", intent: "C", pos1: 10, pos2: null, pos3: null, volume: 20, kd: 6, cpc: 13.50, com: 0.65, results: "88K", category: "unique" },
  { keyword: "when to upgrade electrical panel", intent: "I", pos1: 11, pos2: null, pos3: null, volume: 60, kd: 18, cpc: 11.20, com: 0.58, results: "350K", category: "unique" },
  { keyword: "fpl electrical upgrade venice", intent: "C", pos1: 12, pos2: null, pos3: null, volume: 20, kd: 5, cpc: 12.40, com: 0.62, results: "68K", category: "unique" },
  { keyword: "child proof electrical outlet venice", intent: "C", pos1: 13, pos2: null, pos3: null, volume: 10, kd: 3, cpc: 9.80, com: 0.50, results: "42K", category: "unique" },
  { keyword: "electrical contractor near osprey fl", intent: "C", pos1: 14, pos2: null, pos3: null, volume: 20, kd: 9, cpc: 20.10, com: 0.78, results: "95K", category: "unique" },
  { keyword: "nokomis electrician", intent: "C", pos1: 15, pos2: null, pos3: null, volume: 30, kd: 11, cpc: 22.30, com: 0.82, results: "110K", category: "unique" },
  { keyword: "florida electrical code 2024", intent: "I", pos1: 16, pos2: null, pos3: null, volume: 70, kd: 20, cpc: 8.50, com: 0.45, results: "280K", category: "unique" },
  { keyword: "electrical upgrade for ev charger", intent: "I", pos1: 17, pos2: null, pos3: null, volume: 80, kd: 22, cpc: 25.60, com: 0.85, results: "390K", category: "unique" },
  { keyword: "electrician englewood fl", intent: "C", pos1: 18, pos2: null, pos3: null, volume: 50, kd: 15, cpc: 23.40, com: 0.84, results: "175K", category: "unique" },
  { keyword: "track lighting installation cost florida", intent: "I", pos1: 19, pos2: null, pos3: null, volume: 20, kd: 7, cpc: 13.20, com: 0.63, results: "98K", category: "unique" },
  { keyword: "electrical fire prevention tips", intent: "I", pos1: 20, pos2: null, pos3: null, volume: 40, kd: 10, cpc: 6.80, com: 0.40, results: "220K", category: "unique" },
  { keyword: "island walk electrical venice", intent: "C", pos1: 21, pos2: null, pos3: null, volume: 10, kd: 2, cpc: 0.00, com: 0, results: "18K", category: "unique" },
  { keyword: "venetian golf electrical service", intent: "C", pos1: 22, pos2: null, pos3: null, volume: 10, kd: 3, cpc: 0.00, com: 0, results: "22K", category: "unique" },
  { keyword: "plantation golf electrician venice", intent: "C", pos1: 23, pos2: null, pos3: null, volume: 10, kd: 2, cpc: 0.00, com: 0, results: "15K", category: "unique" },
  { keyword: "south venice electrical repair", intent: "C", pos1: 24, pos2: null, pos3: null, volume: 20, kd: 6, cpc: 18.90, com: 0.74, results: "65K", category: "unique" },
  { keyword: "electric water heater install venice", intent: "C", pos1: 25, pos2: null, pos3: null, volume: 20, kd: 8, cpc: 17.40, com: 0.73, results: "78K", category: "unique" },
  { keyword: "home generator sizing florida", intent: "I", pos1: 26, pos2: null, pos3: null, volume: 50, kd: 16, cpc: 19.80, com: 0.79, results: "185K", category: "unique" },
  { keyword: "led conversion venice fl", intent: "C", pos1: 27, pos2: null, pos3: null, volume: 10, kd: 4, cpc: 11.50, com: 0.56, results: "42K", category: "unique" },
  { keyword: "aluminum wiring dangers florida", intent: "I", pos1: 28, pos2: null, pos3: null, volume: 30, kd: 9, cpc: 14.70, com: 0.67, results: "120K", category: "unique" },
  { keyword: "electrical estimate venice florida", intent: "C", pos1: 29, pos2: null, pos3: null, volume: 10, kd: 3, cpc: 12.80, com: 0.60, results: "35K", category: "unique" },
  { keyword: "code compliant electrical venice fl", intent: "C", pos1: 30, pos2: null, pos3: null, volume: 10, kd: 5, cpc: 15.20, com: 0.68, results: "52K", category: "unique" },
  { keyword: "energy efficient lighting florida", intent: "I", pos1: 31, pos2: null, pos3: null, volume: 40, kd: 13, cpc: 10.40, com: 0.55, results: "240K", category: "unique" },
  { keyword: "hurricane generator installation fl", intent: "C", pos1: 32, pos2: null, pos3: null, volume: 60, kd: 19, cpc: 24.50, com: 0.86, results: "195K", category: "unique" },
  { keyword: "electric panel inspection florida", intent: "I", pos1: 33, pos2: null, pos3: null, volume: 30, kd: 8, cpc: 13.90, com: 0.64, results: "145K", category: "unique" },
  { keyword: "grounding rod installation venice fl", intent: "C", pos1: 34, pos2: null, pos3: null, volume: 10, kd: 4, cpc: 14.30, com: 0.66, results: "38K", category: "unique" },
  { keyword: "spa electrical hookup venice", intent: "C", pos1: 35, pos2: null, pos3: null, volume: 10, kd: 5, cpc: 16.10, com: 0.70, results: "45K", category: "unique" },
  { keyword: "electric dryer outlet install venice", intent: "C", pos1: 36, pos2: null, pos3: null, volume: 10, kd: 3, cpc: 12.10, com: 0.58, results: "32K", category: "unique" },
  { keyword: "bird key electrician sarasota", intent: "C", pos1: 37, pos2: null, pos3: null, volume: 10, kd: 6, cpc: 21.40, com: 0.80, results: "28K", category: "unique" },
  { keyword: "electrical rewire mobile home venice", intent: "C", pos1: 38, pos2: null, pos3: null, volume: 10, kd: 7, cpc: 18.20, com: 0.73, results: "22K", category: "unique" },
  { keyword: "condo electrical upgrade venice fl", intent: "C", pos1: 39, pos2: null, pos3: null, volume: 20, kd: 8, cpc: 19.50, com: 0.76, results: "55K", category: "unique" },
  { keyword: "patio lighting design venice florida", intent: "C", pos1: 40, pos2: null, pos3: null, volume: 10, kd: 5, cpc: 14.60, com: 0.67, results: "48K", category: "unique" },
  { keyword: "electrical safety audit florida", intent: "I", pos1: 41, pos2: null, pos3: null, volume: 20, kd: 10, cpc: 16.70, com: 0.72, results: "85K", category: "unique" },
  { keyword: "home automation wiring venice", intent: "C", pos1: 42, pos2: null, pos3: null, volume: 20, kd: 12, cpc: 20.30, com: 0.78, results: "92K", category: "unique" },
  { keyword: "florida license electrician lookup", intent: "I", pos1: 43, pos2: null, pos3: null, volume: 50, kd: 15, cpc: 7.90, com: 0.42, results: "165K", category: "unique" },
  { keyword: "underground wiring repair venice fl", intent: "C", pos1: 44, pos2: null, pos3: null, volume: 10, kd: 6, cpc: 17.80, com: 0.72, results: "35K", category: "unique" },
  { keyword: "dock power installation venice fl", intent: "C", pos1: 45, pos2: null, pos3: null, volume: 10, kd: 7, cpc: 19.10, com: 0.75, results: "28K", category: "unique" },
  { keyword: "electric stove hookup venice florida", intent: "C", pos1: 46, pos2: null, pos3: null, volume: 10, kd: 4, cpc: 13.40, com: 0.62, results: "32K", category: "unique" },
  { keyword: "affordable electrician venice area", intent: "C", pos1: 47, pos2: null, pos3: null, volume: 20, kd: 9, cpc: 22.70, com: 0.83, results: "75K", category: "unique" },
  { keyword: "night lighting installation venice", intent: "C", pos1: 48, pos2: null, pos3: null, volume: 10, kd: 5, cpc: 13.80, com: 0.64, results: "40K", category: "unique" },
  { keyword: "electrical panel fire risk florida", intent: "I", pos1: 50, pos2: null, pos3: null, volume: 30, kd: 11, cpc: 9.20, com: 0.48, results: "135K", category: "unique" },
];

const tabs = [
  { id: "shared", label: "Shared", count: allKeywords.filter(k => k.category === "shared").length, desc: "Keywords all domains rank for" },
  { id: "missing", label: "Missing", count: allKeywords.filter(k => k.category === "missing").length, desc: "Keywords your competitors rank for, but you don't" },
  { id: "weak", label: "Weak", count: allKeywords.filter(k => k.category === "weak").length, desc: "Keywords where you rank lower than all competitors" },
  { id: "strong", label: "Strong", count: allKeywords.filter(k => k.category === "strong").length, desc: "Keywords where you rank higher than all competitors" },
  { id: "untapped", label: "Untapped", count: allKeywords.filter(k => k.category === "untapped").length, desc: "Keywords only one competitor ranks for" },
  { id: "unique", label: "Unique", count: allKeywords.filter(k => k.category === "unique").length, desc: "Keywords only you rank for" },
  { id: "all", label: "All", count: allKeywords.length, desc: "All keywords" },
];

const domains = [
  { key: "pos1", name: "akelectricalfl.com", color: "#4C8BF5", isYou: true },
  { key: "pos2", name: "veniceelectrician.com", color: "#34A853" },
  { key: "pos3", name: "palmislandelectric.com", color: "#F5A623" },
];

function IntentBadge({ intent }) {
  const colors = {
    C: { bg: "#FFF3E0", text: "#E65100", border: "#FFB74D" },
    I: { bg: "#E8F5E9", text: "#2E7D32", border: "#81C784" },
    N: { bg: "#E3F2FD", text: "#1565C0", border: "#64B5F6" },
    T: { bg: "#F3E5F5", text: "#6A1B9A", border: "#BA68C8" },
  };
  const c = colors[intent] || colors.C;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", justifyContent: "center",
      width: 24, height: 24, borderRadius: 4, fontSize: 11, fontWeight: 700,
      background: c.bg, color: c.text, border: `1px solid ${c.border}`,
    }}>{intent}</span>
  );
}

function KDBar({ value }) {
  const getColor = (v) => {
    if (v <= 14) return "#4CAF50";
    if (v <= 29) return "#FFC107";
    if (v <= 49) return "#FF9800";
    if (v <= 69) return "#FF5722";
    return "#D32F2F";
  };
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <div style={{ width: 36, height: 8, borderRadius: 4, background: "#E8E8E8", overflow: "hidden" }}>
        <div style={{ width: `${value}%`, height: "100%", borderRadius: 4, background: getColor(value), transition: "width 0.3s" }} />
      </div>
      <span style={{ fontSize: 13, color: "#333", minWidth: 20 }}>{value}</span>
    </div>
  );
}

function PositionCell({ value, isYou }) {
  if (value === null) return <span style={{ color: "#CCC", fontSize: 13 }}>—</span>;
  const getBg = (v) => {
    if (v <= 3) return isYou ? "#E8F5E9" : "#F1F8E9";
    if (v <= 10) return isYou ? "#E3F2FD" : "#FFF8E1";
    if (v <= 20) return isYou ? "#FFF3E0" : "#FFF3E0";
    return isYou ? "#FFEBEE" : "#FCE4EC";
  };
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", justifyContent: "center",
      minWidth: 32, padding: "2px 8px", borderRadius: 4,
      background: getBg(value), fontSize: 13, fontWeight: 500, color: "#333",
    }}>{value}</span>
  );
}

export default function KeywordGapAnalysis() {
  const [activeTab, setActiveTab] = useState("shared");
  const [sortField, setSortField] = useState("pos1");
  const [sortDir, setSortDir] = useState("asc");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedRows, setSelectedRows] = useState(new Set());
  const [page, setPage] = useState(1);
  const perPage = 20;

  const filtered = useMemo(() => {
    let data = activeTab === "all" ? allKeywords : allKeywords.filter(k => k.category === activeTab);
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      data = data.filter(k => k.keyword.toLowerCase().includes(q));
    }
    data.sort((a, b) => {
      let aVal = a[sortField], bVal = b[sortField];
      if (aVal === null) aVal = 999;
      if (bVal === null) bVal = 999;
      if (typeof aVal === "string") return sortDir === "asc" ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
      return sortDir === "asc" ? aVal - bVal : bVal - aVal;
    });
    return data;
  }, [activeTab, sortField, sortDir, searchQuery]);

  const totalPages = Math.ceil(filtered.length / perPage);
  const pageData = filtered.slice((page - 1) * perPage, page * perPage);

  const handleSort = (field) => {
    if (sortField === field) setSortDir(d => d === "asc" ? "desc" : "asc");
    else { setSortField(field); setSortDir("asc"); }
  };

  const toggleRow = (keyword) => {
    setSelectedRows(prev => {
      const next = new Set(prev);
      next.has(keyword) ? next.delete(keyword) : next.add(keyword);
      return next;
    });
  };

  const toggleAll = () => {
    if (selectedRows.size === pageData.length) setSelectedRows(new Set());
    else setSelectedRows(new Set(pageData.map(k => k.keyword)));
  };

  const SortIcon = ({ field }) => {
    if (sortField !== field) return <span style={{ color: "#CCC", marginLeft: 4 }}>↕</span>;
    return <span style={{ color: "#4C8BF5", marginLeft: 4 }}>{sortDir === "asc" ? "↑" : "↓"}</span>;
  };

  const currentTab = tabs.find(t => t.id === activeTab);

  return (
    <div style={{ fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif", background: "#F5F6FA", minHeight: "100vh", padding: 24 }}>
      {/* Header */}
      <div style={{ background: "#fff", borderRadius: 12, padding: 24, marginBottom: 20, boxShadow: "0 1px 3px rgba(0,0,0,0.08)" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
          <div>
            <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: "#1a1a2e" }}>Keyword Gap Analysis</h1>
            <p style={{ margin: "4px 0 0", fontSize: 14, color: "#666" }}>All keyword details for: <strong>akelectricalfl.com</strong></p>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, background: "#F0F4FF", padding: "6px 14px", borderRadius: 8 }}>
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#4C8BF5" }} />
            <span style={{ fontSize: 13, fontWeight: 600, color: "#4C8BF5" }}>You</span>
          </div>
        </div>

        {/* Domain chips */}
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          {domains.map(d => (
            <div key={d.key} style={{
              display: "flex", alignItems: "center", gap: 8, padding: "8px 16px",
              borderRadius: 8, background: d.isYou ? "#F0F4FF" : "#F9F9F9",
              border: `1px solid ${d.isYou ? "#4C8BF5" : "#E0E0E0"}`,
            }}>
              <span style={{ width: 10, height: 10, borderRadius: "50%", background: d.color }} />
              <span style={{ fontSize: 13, fontWeight: d.isYou ? 600 : 400, color: "#333" }}>{d.name}</span>
              {d.isYou && <span style={{ fontSize: 10, background: "#4C8BF5", color: "#fff", padding: "1px 6px", borderRadius: 4, fontWeight: 600 }}>YOU</span>}
            </div>
          ))}
        </div>
      </div>

      {/* Tabs + Search */}
      <div style={{ background: "#fff", borderRadius: 12, padding: "16px 24px", marginBottom: 2, boxShadow: "0 1px 3px rgba(0,0,0,0.08)" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
            {tabs.map(t => (
              <button key={t.id} onClick={() => { setActiveTab(t.id); setPage(1); setSelectedRows(new Set()); }}
                title={t.desc}
                style={{
                  padding: "8px 16px", borderRadius: 8, border: "1px solid",
                  borderColor: activeTab === t.id ? "#4C8BF5" : "#E0E0E0",
                  background: activeTab === t.id ? "#4C8BF5" : "#fff",
                  color: activeTab === t.id ? "#fff" : "#555",
                  fontSize: 13, fontWeight: 600, cursor: "pointer",
                  transition: "all 0.2s",
                }}>
                {t.label} <span style={{
                  marginLeft: 4, padding: "1px 6px", borderRadius: 10,
                  background: activeTab === t.id ? "rgba(255,255,255,0.25)" : "#F0F0F0",
                  fontSize: 11,
                }}>{t.count}</span>
              </button>
            ))}
          </div>
          <div style={{ position: "relative" }}>
            <input value={searchQuery} onChange={e => { setSearchQuery(e.target.value); setPage(1); }}
              placeholder="Filter keywords..." style={{
                padding: "8px 12px 8px 34px", borderRadius: 8, border: "1px solid #E0E0E0",
                fontSize: 13, width: 220, outline: "none",
              }} />
            <span style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", color: "#999", fontSize: 14 }}>🔍</span>
          </div>
        </div>
        {currentTab && (
          <p style={{ margin: "8px 0 0", fontSize: 12, color: "#888" }}>{currentTab.desc}</p>
        )}
      </div>

      {/* Table */}
      <div style={{ background: "#fff", borderRadius: "0 0 12px 12px", boxShadow: "0 1px 3px rgba(0,0,0,0.08)", overflow: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ background: "#FAFBFC", borderBottom: "2px solid #E8E8E8" }}>
              <th style={{ padding: "12px 16px", width: 40 }}>
                <input type="checkbox" checked={selectedRows.size === pageData.length && pageData.length > 0}
                  onChange={toggleAll} style={{ cursor: "pointer" }} />
              </th>
              <th style={{ padding: "12px 16px", textAlign: "left", cursor: "pointer", userSelect: "none", minWidth: 260 }}
                onClick={() => handleSort("keyword")}>
                Keyword <SortIcon field="keyword" />
              </th>
              <th style={{ padding: "12px 16px", textAlign: "center", width: 60 }}>Intent</th>
              {domains.map(d => (
                <th key={d.key} style={{ padding: "12px 8px", textAlign: "center", cursor: "pointer", userSelect: "none", minWidth: 90 }}
                  onClick={() => handleSort(d.key)}>
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 2 }}>
                    <span style={{ width: 8, height: 8, borderRadius: "50%", background: d.color }} />
                    <span style={{ fontSize: 11, color: "#666", maxWidth: 100, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {d.name.replace(".com", "...")}
                    </span>
                  </div>
                  <SortIcon field={d.key} />
                </th>
              ))}
              <th style={{ padding: "12px 8px", textAlign: "right", cursor: "pointer", userSelect: "none" }}
                onClick={() => handleSort("volume")}>Volume <SortIcon field="volume" /></th>
              <th style={{ padding: "12px 8px", textAlign: "center", cursor: "pointer", userSelect: "none", minWidth: 80 }}
                onClick={() => handleSort("kd")}>KD% <SortIcon field="kd" /></th>
              <th style={{ padding: "12px 8px", textAlign: "right", cursor: "pointer", userSelect: "none" }}
                onClick={() => handleSort("cpc")}>CPC <SortIcon field="cpc" /></th>
              <th style={{ padding: "12px 8px", textAlign: "right", cursor: "pointer", userSelect: "none" }}
                onClick={() => handleSort("com")}>Com. <SortIcon field="com" /></th>
              <th style={{ padding: "12px 8px", textAlign: "right", cursor: "pointer", userSelect: "none" }}
                onClick={() => handleSort("results")}>Results <SortIcon field="results" /></th>
            </tr>
          </thead>
          <tbody>
            {pageData.map((row, i) => (
              <tr key={row.keyword} style={{
                borderBottom: "1px solid #F0F0F0",
                background: selectedRows.has(row.keyword) ? "#F0F7FF" : i % 2 === 0 ? "#fff" : "#FAFBFC",
                transition: "background 0.15s",
              }}
                onMouseEnter={e => { if (!selectedRows.has(row.keyword)) e.currentTarget.style.background = "#F5F8FF"; }}
                onMouseLeave={e => { if (!selectedRows.has(row.keyword)) e.currentTarget.style.background = i % 2 === 0 ? "#fff" : "#FAFBFC"; }}
              >
                <td style={{ padding: "10px 16px", textAlign: "center" }}>
                  <input type="checkbox" checked={selectedRows.has(row.keyword)}
                    onChange={() => toggleRow(row.keyword)} style={{ cursor: "pointer" }} />
                </td>
                <td style={{ padding: "10px 16px", fontWeight: 500, color: "#1a1a2e" }}>{row.keyword}</td>
                <td style={{ padding: "10px 8px", textAlign: "center" }}><IntentBadge intent={row.intent} /></td>
                {domains.map(d => (
                  <td key={d.key} style={{ padding: "10px 8px", textAlign: "center" }}>
                    <PositionCell value={row[d.key]} isYou={d.isYou} />
                  </td>
                ))}
                <td style={{ padding: "10px 8px", textAlign: "right", fontWeight: 600, color: "#333" }}>{row.volume.toLocaleString()}</td>
                <td style={{ padding: "10px 8px" }}><KDBar value={row.kd} /></td>
                <td style={{ padding: "10px 8px", textAlign: "right", color: "#555" }}>{row.cpc.toFixed(2)}</td>
                <td style={{ padding: "10px 8px", textAlign: "right", color: "#555" }}>{row.com}</td>
                <td style={{ padding: "10px 8px", textAlign: "right", color: "#555" }}>{row.results}</td>
              </tr>
            ))}
            {pageData.length === 0 && (
              <tr><td colSpan={10} style={{ padding: 40, textAlign: "center", color: "#999" }}>No keywords found matching your criteria.</td></tr>
            )}
          </tbody>
        </table>

        {/* Pagination */}
        {totalPages > 1 && (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 24px", borderTop: "1px solid #F0F0F0" }}>
            <span style={{ fontSize: 12, color: "#888" }}>
              Showing {(page - 1) * perPage + 1}–{Math.min(page * perPage, filtered.length)} of {filtered.length} keywords
            </span>
            <div style={{ display: "flex", gap: 4 }}>
              <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
                style={{ padding: "6px 12px", borderRadius: 6, border: "1px solid #E0E0E0", background: page === 1 ? "#F5F5F5" : "#fff", cursor: page === 1 ? "default" : "pointer", fontSize: 12 }}>
                ← Prev
              </button>
              {Array.from({ length: totalPages }, (_, i) => i + 1).map(p => (
                <button key={p} onClick={() => setPage(p)}
                  style={{
                    padding: "6px 10px", borderRadius: 6, border: "1px solid",
                    borderColor: page === p ? "#4C8BF5" : "#E0E0E0",
                    background: page === p ? "#4C8BF5" : "#fff",
                    color: page === p ? "#fff" : "#555",
                    cursor: "pointer", fontSize: 12, fontWeight: page === p ? 600 : 400,
                  }}>{p}</button>
              ))}
              <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}
                style={{ padding: "6px 12px", borderRadius: 6, border: "1px solid #E0E0E0", background: page === totalPages ? "#F5F5F5" : "#fff", cursor: page === totalPages ? "default" : "pointer", fontSize: 12 }}>
                Next →
              </button>
            </div>
          </div>
        )}

        {/* Selected count bar */}
        {selectedRows.size > 0 && (
          <div style={{
            position: "sticky", bottom: 0, background: "#4C8BF5", color: "#fff",
            padding: "10px 24px", display: "flex", alignItems: "center", justifyContent: "space-between",
            borderRadius: "0 0 12px 12px",
          }}>
            <span style={{ fontSize: 13, fontWeight: 600 }}>{selectedRows.size} keyword{selectedRows.size > 1 ? "s" : ""} selected</span>
            <button onClick={() => setSelectedRows(new Set())}
              style={{ padding: "4px 12px", borderRadius: 6, border: "1px solid rgba(255,255,255,0.4)", background: "transparent", color: "#fff", cursor: "pointer", fontSize: 12 }}>
              Clear selection
            </button>
          </div>
        )}
      </div>

      {/* Legend */}
      <div style={{ marginTop: 16, padding: "16px 24px", background: "#fff", borderRadius: 12, boxShadow: "0 1px 3px rgba(0,0,0,0.08)" }}>
        <div style={{ display: "flex", gap: 24, flexWrap: "wrap", fontSize: 12, color: "#666" }}>
          <span><strong>Intent:</strong></span>
          <span><IntentBadge intent="C" /> Commercial</span>
          <span><IntentBadge intent="I" /> Informational</span>
          <span><IntentBadge intent="N" /> Navigational</span>
          <span><IntentBadge intent="T" /> Transactional</span>
          <span style={{ marginLeft: "auto", color: "#999" }}>Data for akelectricalfl.com keyword gap analysis</span>
        </div>
      </div>
    </div>
  );
}