"""Translates raw Fantrax API responses into human-readable data.

The Fantrax internal API returns data with cryptic IDs, nested structures,
and encoded formats. This module decodes everything into plain English
so an AI can understand it without any Fantrax-specific knowledge.

NOTE: Fantrax responses often mix dicts, lists, bools, and ints in the
same parent object. Every .get() or .items() call must guard against
non-dict values to avoid "'bool' object has no attribute 'items'" crashes.
"""

from __future__ import annotations


def _as_dict(val: object) -> dict:
    """Return val if it's a dict, otherwise empty dict. Prevents crashes on bools/ints."""
    return val if isinstance(val, dict) else {}


def translate_standings(raw: dict) -> dict:
    """Convert raw standings response into readable standings."""
    if not isinstance(raw, dict) or "tableList" not in raw:
        return {"error": "No standings data", "raw_keys": list(raw.keys()) if isinstance(raw, dict) else []}

    team_info = _as_dict(raw.get("fantasyTeamInfo"))
    result = {"teams": [], "period_matchups": {}}

    # Parse standings table
    for table in raw["tableList"]:
        header_cells = table.get("header", {}).get("cells", [])
        header_keys = [c.get("key", c.get("shortName", f"col{i}")) for i, c in enumerate(header_cells)]
        header_names = [c.get("name", c.get("shortName", "")) for c in header_cells]

        for row in table.get("rows", []):
            fixed = row.get("fixedCells", [])
            cells = row.get("cells", [])

            rank = fixed[0]["content"] if len(fixed) > 0 else "?"
            team_id = fixed[1].get("teamId", "") if len(fixed) > 1 else ""
            team_name = fixed[1].get("content", "") if len(fixed) > 1 else ""

            team_record = {
                "rank": rank,
                "team_name": team_name,
                "team_id": team_id,
            }

            for i, cell in enumerate(cells):
                key = header_keys[i] if i < len(header_keys) else f"col{i}"
                name = header_names[i] if i < len(header_names) else key
                team_record[key] = {
                    "label": name,
                    "value": cell.get("content", ""),
                }

            result["teams"].append(team_record)

    # Parse current matchups
    matchup_ids = _as_dict(raw.get("matchupIdsPerTeam"))
    matchup_pairs = set()
    for tid, matchups in matchup_ids.items():
        if not isinstance(matchups, list):
            continue
        for mid in matchups:
            matchup_pairs.add(mid)

    for mid in matchup_pairs:
        parts = mid.split("_")
        if len(parts) == 2:
            away_name = team_info.get(parts[0], {}).get("name", parts[0])
            home_name = team_info.get(parts[1], {}).get("name", parts[1])
            result["period_matchups"][mid] = f"{away_name} vs {home_name}"

    return result


def _build_cat_map(raw: dict) -> dict[str, dict[str, str]]:
    """Build a mapping from ALL forms of category ID to human-readable stat name.

    Fantrax uses several ID formats:
      - Simple scipId: "0330"
      - Compound key: "10#0330#-1" (group#scipId#variant)
    We index by all forms so lookups always succeed.
    """
    cat_map: dict[str, dict[str, str]] = {}

    for group_id, group_headers in raw.get("tableHeaderTopLevelPerScGroup", {}).items():
        if not isinstance(group_headers, list):
            continue
        for header in group_headers:
            scip_id = header.get("scipId", "")
            short_name = header.get("shortName", "")
            full_name = header.get("name", short_name)
            if not scip_id:
                continue

            info = {"short": short_name, "name": full_name}
            # Index by simple scipId
            cat_map[scip_id] = info
            # Index by compound key forms: "group#scipId#-1", "group#scipId#0", etc.
            for variant in ("-1", "0", "1"):
                cat_map[f"{group_id}#{scip_id}#{variant}"] = info

    # Also try tableHeaders if present (alternate response shape)
    for header in raw.get("tableHeaders", []):
        scip_id = header.get("scipId", "")
        short_name = header.get("shortName", "")
        if scip_id and scip_id not in cat_map:
            cat_map[scip_id] = {"short": short_name, "name": header.get("name", short_name)}

    return cat_map


def _build_scorer_map(raw: dict) -> dict[str, dict]:
    """Extract player info from scorerMap, handling variable nesting depth."""
    scorer_map = {}

    def _extract_scorer(obj: object) -> None:
        """Recursively walk the scorerMap to find scorer entries."""
        if isinstance(obj, dict):
            # If this dict has a "scorer" key, it's a player entry
            if "scorer" in obj and isinstance(obj["scorer"], dict):
                scorer = obj["scorer"]
                sid = scorer.get("scorerId", "")
                if sid:
                    scorer_map[sid] = {
                        "name": scorer.get("name", ""),
                        "short_name": scorer.get("shortName", ""),
                        "team": scorer.get("teamShortName", ""),
                        "positions": scorer.get("posShortNames", ""),
                    }
            else:
                for v in obj.values():
                    _extract_scorer(v)
        elif isinstance(obj, list):
            for item in obj:
                _extract_scorer(item)

    _extract_scorer(raw.get("scorerMap", {}))
    return scorer_map


def _decode_player_stats(stat_data: object, cat_map: dict) -> tuple[float, dict]:
    """Extract fantasy points and stat values from a player's stat data.

    Handles multiple response formats:
    - object1/object2 with list of {scipId, sv, av} dicts
    - object1/object2 with a plain dict of {statId: value}
    - Plain dict of {statId: value} at top level
    """
    fantasy_points = 0.0
    stats: dict[str, dict] = {}

    if isinstance(stat_data, dict):
        fantasy_points = stat_data.get("object1", 0) or 0
        obj2 = stat_data.get("object2", stat_data)

        if isinstance(obj2, list):
            # Format: [{scipId: "xxx", sv: "1", av: 1}, ...]
            for entry in obj2:
                if isinstance(entry, dict):
                    scip_id = entry.get("scipId", "")
                    stat_info = cat_map.get(scip_id, {})
                    stat_name = stat_info.get("short", scip_id)
                    stats[stat_name] = {
                        "value": entry.get("sv", ""),
                        "numeric": entry.get("av", 0),
                    }
        elif isinstance(obj2, dict):
            # Format: {"10#0330#-1": 1, "10#0170#-1": 3, ...}
            for stat_id, value in obj2.items():
                if stat_id in ("object1", "object2"):
                    continue
                stat_info = cat_map.get(stat_id, {})
                stat_name = stat_info.get("short", stat_id)
                if isinstance(value, dict):
                    stats[stat_name] = {
                        "value": value.get("sv", str(value.get("av", ""))),
                        "numeric": value.get("av", 0),
                    }
                else:
                    stats[stat_name] = {"value": str(value), "numeric": value}

    return fantasy_points, stats


def translate_live_scoring(raw: dict) -> dict:
    """Convert raw live scoring response into readable player stats and matchups."""
    if not raw:
        return {"error": "No scoring data"}

    result = {
        "date": raw.get("date", ""),
        "display_period": raw.get("displayPeriod", ""),
        "all_events_finished": raw.get("allEventsFinished", False),
        "scoring_categories": {},
        "teams": {},
        "matchups": [],
        "player_stats": {},
    }

    # ── Decode scoring categories ────────────────────────────────────
    for group in raw.get("scoringCategoryGroups", []):
        group_id = group.get("id", "")
        group_name = group.get("name", "")
        result["scoring_categories"][group_id] = group_name

    cat_map = _build_cat_map(raw)
    result["stat_id_to_name"] = {
        k: v for k, v in cat_map.items() if "#" not in k  # Only show simple IDs in legend
    }

    # ── Decode team info ─────────────────────────────────────────────
    team_info = _as_dict(raw.get("fantasyTeamInfo"))
    for tid, info in team_info.items():
        if not isinstance(tid, str) or tid.startswith("-"):
            continue
        if isinstance(info, dict):
            result["teams"][tid] = info.get("name", tid)
        elif isinstance(info, str):
            result["teams"][tid] = info

    # ── Decode player info from scorerMap ────────────────────────────
    scorer_map = _build_scorer_map(raw)

    # ── Build team ID → roster mapping from fantasyTeams ────────────
    # fantasyTeams maps team_id → list of scorer IDs on each team
    team_rosters: dict[str, list[str]] = {}
    fantasy_teams = raw.get("fantasyTeams", {})
    if isinstance(fantasy_teams, dict):
        for tid, roster_data in fantasy_teams.items():
            if not isinstance(tid, str) or tid.startswith("-"):
                continue
            if isinstance(roster_data, list):
                team_rosters[tid] = roster_data
            elif isinstance(roster_data, dict):
                # Could be nested: {"scorerIds": [...]} or similar
                for v in roster_data.values():
                    if isinstance(v, list):
                        team_rosters[tid] = v
                        break
            # Skip bools, ints, or other non-collection types

    # ── Extract individual player stats from allPlayerStats ──────────
    # allPlayerStats is a flat map: scorer_id → stat data for ALL players
    all_player_stats_raw = _as_dict(raw.get("allPlayerStats"))

    # ── Decode per-team player stats ─────────────────────────────────
    stats_per_team = _as_dict(_as_dict(raw.get("statsPerTeam")).get("allTeamsStats"))
    for team_id, team_data in stats_per_team.items():
        if not isinstance(team_id, str) or team_id.startswith("-"):
            continue
        if not isinstance(team_data, dict):
            continue
        team_name = result["teams"].get(team_id, team_id)

        # Collect players from ALL roster status groups, not just ACTIVE
        all_stats_map: dict = {}
        all_season_totals: dict = {}
        for status_key, status_data in team_data.items():
            if not isinstance(status_data, dict):
                continue
            sm = _as_dict(status_data.get("statsMap"))
            if sm:
                all_stats_map.update(sm)
            st = _as_dict(status_data.get("seasonTotals"))
            if st:
                for k, v in st.items():
                    if k not in all_season_totals:
                        all_season_totals[k] = v

        # Fallback: if team_data itself has statsMap (flat structure)
        if not all_stats_map:
            all_stats_map = _as_dict(team_data.get("statsMap"))
        if not all_season_totals:
            all_season_totals = _as_dict(team_data.get("seasonTotals"))

        # Filter out aggregate keys — only real player IDs
        player_stats_map = {
            k: v for k, v in all_stats_map.items() if not k.startswith("_")
        }

        # If statsPerTeam has no individual players, use allPlayerStats + fantasyTeams
        if not player_stats_map and all_player_stats_raw and team_id in team_rosters:
            roster_ids = team_rosters[team_id]
            for sid in roster_ids:
                if sid in all_player_stats_raw:
                    player_stats_map[sid] = all_player_stats_raw[sid]

        team_players = []
        for scorer_id, stat_data in player_stats_map.items():
            player_info = scorer_map.get(scorer_id, {"name": scorer_id})
            fantasy_points, player_stat_values = _decode_player_stats(stat_data, cat_map)

            team_players.append({
                "player_name": player_info.get("name", scorer_id),
                "mlb_team": player_info.get("team", ""),
                "positions": player_info.get("positions", ""),
                "fantasy_points": fantasy_points,
                "stats": player_stat_values,
            })

        # Team totals
        team_totals = {}
        for cat_id, totals in all_season_totals.items():
            if not isinstance(totals, dict):
                continue
            if cat_id.startswith("_"):
                if cat_id == "_ALL":
                    label = "All Categories Total"
                elif cat_id == "_10":
                    label = "Hitting Total"
                elif cat_id == "_20":
                    label = "Pitching Total"
                else:
                    label = cat_id
                team_totals[label] = {
                    "period_points": totals.get("o2", 0),
                    "season_points": totals.get("o3", 0),
                }
            else:
                stat_info = cat_map.get(cat_id, {})
                stat_name = stat_info.get("short", cat_id)
                team_totals[stat_name] = {
                    "period_points": totals.get("o2", 0),
                    "season_points": totals.get("o3", 0),
                }

        result["player_stats"][team_name] = {
            "team_id": team_id,
            "players": sorted(team_players, key=lambda p: p["fantasy_points"], reverse=True),
            "category_points": team_totals,
        }

    # ── Decode matchups ──────────────────────────────────────────────
    matchup_map = _as_dict(raw.get("matchupMap"))
    matchup_list = raw.get("matchups", []) if isinstance(raw.get("matchups"), list) else []

    for matchup_id in matchup_list:
        parts = matchup_id.split("_")
        if len(parts) != 2:
            continue

        away_id, home_id = parts
        away_name = result["teams"].get(away_id, away_id)
        home_name = result["teams"].get(home_id, home_id)

        matchup_data = matchup_map.get(matchup_id, {})

        matchup = {
            "matchup_id": matchup_id,
            "away_team": away_name,
            "home_team": home_name,
        }

        # Parse category-by-category results if available
        if isinstance(matchup_data, dict):
            categories = []
            for cat_id, cat_result in matchup_data.items():
                stat_info = cat_map.get(cat_id, {})
                stat_name = stat_info.get("short", cat_id)
                categories.append({
                    "category": stat_name,
                    "result": cat_result,
                })
            matchup["category_results"] = categories

        result["matchups"].append(matchup)

    return result


def translate_transactions(raw: dict) -> dict:
    """Convert raw transaction response into readable transaction history."""
    if not raw:
        return {"error": "No transaction data"}

    result = {
        "total_transactions": raw.get("paginatedResultSet", {}).get("totalNumResults", 0),
        "filter": raw.get("filterSettings", {}).get("view", ""),
        "transactions": [],
    }

    table = raw.get("table", {})
    rows = table.get("rows", [])

    # Group rows by txSetId (multiple rows = multi-player transaction)
    grouped = {}
    for row in rows:
        tx_id = row.get("txSetId", "unknown")
        if tx_id not in grouped:
            grouped[tx_id] = []
        grouped[tx_id].append(row)

    for tx_id, tx_rows in grouped.items():
        first = tx_rows[0]
        cells = first.get("cells", [])

        team_name = cells[0].get("content", "") if cells else ""
        date_str = cells[1].get("content", "") if len(cells) > 1 else ""
        period = cells[2].get("content", "") if len(cells) > 2 else ""

        players = []
        for row in tx_rows:
            scorer = row.get("scorer", {})
            player_name = scorer.get("name", "Unknown")
            player_team = scorer.get("teamShortName", "")
            positions = scorer.get("posShortNames", "")
            tx_code = row.get("transactionCode", "")
            claim_type = row.get("claimType", "")

            action = tx_code
            if tx_code == "CLAIM":
                action = f"Claimed ({claim_type})"
            elif tx_code == "DROP":
                action = "Dropped"

            players.append({
                "player": player_name,
                "mlb_team": player_team,
                "positions": positions,
                "action": action,
            })

        result["transactions"].append({
            "id": tx_id,
            "team": team_name,
            "date": date_str,
            "period": period,
            "type": first.get("transactionType", ""),
            "status": first.get("result", {}).get("content", ""),
            "players": players,
        })

    return result


def translate_team_roster(raw: dict, team_name: str = "") -> dict:
    """Convert raw team roster response into readable roster."""
    if not raw:
        return {"error": "No roster data"}

    # The response structure varies — try common patterns
    result = {"team_name": team_name, "players": []}

    table = raw.get("table", raw.get("tableList", [{}]))
    if isinstance(table, list) and table:
        table = table[0]

    rows = table.get("rows", [])
    header = table.get("header", {}).get("cells", [])
    header_keys = [c.get("shortName", c.get("key", f"col{i}")) for i, c in enumerate(header)]

    for row in rows:
        scorer = row.get("scorer", {})
        cells = row.get("cells", [])

        player = {
            "name": scorer.get("name", ""),
            "mlb_team": scorer.get("teamShortName", ""),
            "positions": scorer.get("posShortNames", ""),
            "stats": {},
        }

        for i, cell in enumerate(cells):
            key = header_keys[i] if i < len(header_keys) else f"stat{i}"
            player["stats"][key] = cell.get("content", cell.get("sv", ""))

        if player["name"]:
            result["players"].append(player)

    return result
