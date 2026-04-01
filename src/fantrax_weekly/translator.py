"""Translates raw Fantrax API responses into human-readable data.

The Fantrax internal API returns data with cryptic IDs, nested structures,
and encoded formats. This module decodes everything into plain English
so an AI can understand it without any Fantrax-specific knowledge.
"""

from __future__ import annotations


def translate_standings(raw: dict) -> dict:
    """Convert raw standings response into readable standings."""
    if not raw or "tableList" not in raw:
        return {"error": "No standings data", "raw_keys": list(raw.keys()) if raw else []}

    team_info = raw.get("fantasyTeamInfo", {})
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
    matchup_ids = raw.get("matchupIdsPerTeam", {})
    matchup_pairs = set()
    for tid, matchups in matchup_ids.items():
        for mid in matchups:
            matchup_pairs.add(mid)

    for mid in matchup_pairs:
        parts = mid.split("_")
        if len(parts) == 2:
            away_name = team_info.get(parts[0], {}).get("name", parts[0])
            home_name = team_info.get(parts[1], {}).get("name", parts[1])
            result["period_matchups"][mid] = f"{away_name} vs {home_name}"

    return result


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
    # Build a mapping from scipId to human-readable stat name
    cat_map = {}
    for group in raw.get("scoringCategoryGroups", []):
        group_id = group.get("id", "")
        group_name = group.get("name", "")
        result["scoring_categories"][group_id] = group_name

    # The table headers contain the actual stat names mapped to category IDs
    for group_headers in raw.get("tableHeaderTopLevelPerScGroup", {}).values():
        if isinstance(group_headers, list):
            for header in group_headers:
                scip_id = header.get("scipId", "")
                short_name = header.get("shortName", "")
                full_name = header.get("name", short_name)
                if scip_id:
                    cat_map[scip_id] = {"short": short_name, "name": full_name}

    result["stat_id_to_name"] = cat_map

    # ── Decode team info ─────────────────────────────────────────────
    team_info = raw.get("fantasyTeamInfo", {})
    for tid, info in team_info.items():
        if tid.startswith("-"):
            continue
        result["teams"][tid] = info.get("name", tid)

    # ── Decode player info from scorerMap ────────────────────────────
    scorer_map = {}
    for _, level1 in raw.get("scorerMap", {}).items():
        if isinstance(level1, dict):
            for _, level2 in level1.items():
                if isinstance(level2, dict):
                    for _, level3 in level2.items():
                        if isinstance(level3, list):
                            for entry in level3:
                                scorer = entry.get("scorer", {})
                                sid = scorer.get("scorerId", "")
                                if sid:
                                    scorer_map[sid] = {
                                        "name": scorer.get("name", ""),
                                        "short_name": scorer.get("shortName", ""),
                                        "team": scorer.get("teamShortName", ""),
                                        "positions": scorer.get("posShortNames", ""),
                                    }

    # ── Decode per-team player stats ─────────────────────────────────
    stats_per_team = raw.get("statsPerTeam", {}).get("allTeamsStats", {})
    for team_id, team_data in stats_per_team.items():
        team_name = result["teams"].get(team_id, team_id)
        if team_id.startswith("-"):
            continue

        active = team_data.get("ACTIVE", {})
        stats_map = active.get("statsMap", {})
        season_totals = active.get("seasonTotals", {})

        team_players = []
        for scorer_id, stat_data in stats_map.items():
            if scorer_id.startswith("_"):
                continue

            player_info = scorer_map.get(scorer_id, {"name": scorer_id})
            stat_entries = stat_data.get("object2", [])
            fantasy_points = stat_data.get("object1", 0)

            player_stats = {
                "player_name": player_info.get("name", scorer_id),
                "mlb_team": player_info.get("team", ""),
                "positions": player_info.get("positions", ""),
                "fantasy_points": fantasy_points,
                "stats": {},
            }

            for entry in stat_entries:
                scip_id = entry.get("scipId", "")
                stat_info = cat_map.get(scip_id, {})
                stat_name = stat_info.get("short", scip_id)
                player_stats["stats"][stat_name] = {
                    "value": entry.get("sv", ""),
                    "numeric": entry.get("av", 0),
                }

            team_players.append(player_stats)

        # Team totals
        team_totals = {}
        for cat_id, totals in season_totals.items():
            if cat_id.startswith("_"):
                label = "Total" if cat_id == "_ALL" else cat_id
                if cat_id == "_ALL":
                    label = "All Categories Total"
                elif cat_id == "_10":
                    label = "Hitting Total"
                elif cat_id == "_20":
                    label = "Pitching Total"
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
    matchup_map = raw.get("matchupMap", {})
    matchup_list = raw.get("matchups", [])

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
