import os
import requests
from dotenv import load_dotenv

def main():
    # Load environment variables from .env
    load_dotenv()

    # Get your Riot Dev Key
    api_key = os.getenv("RIOT_API_KEY")
    if not api_key:
        print("Missing RIOT_API_KEY in .env file.")
        return

    # Prompt user for Riot ID
    riot_id = input("Enter Riot ID (e.g., GameName#TagLine): ").strip()
    try:
        game_name, tag_line = riot_id.split('#')
    except ValueError:
        print("Invalid Riot ID format. Must be GameName#TagLine.")
        return

    # Common headers for all requests
    headers = {
        "X-Riot-Token": api_key
    }

    #
    # 1) Get PUUID from the "Account-V1" endpoint
    #    Using "americas.api.riotgames.com" is often used as a 'global' call for /account/v1
    #    If that fails or returns a 400, you may need to swap to another region for /account/v1 as well.
    #
    account_url = (
        f"https://americas.api.riotgames.com/riot/account/v1/"
        f"accounts/by-riot-id/{game_name}/{tag_line}"
    )
    try:
        r = requests.get(account_url, headers=headers)
        r.raise_for_status()
        account_data = r.json()
        puuid = account_data["puuid"]
        print("ACCOUNT DATA:", account_data)  # Debug: shows gameName, tagLine, etc.
    except Exception as e:
        print(f"Error fetching PUUID: {e}")
        return

    #
    # 2) Find which Valorant shard this PUUID actually uses:
    #    (na, eu, ap, kr, latam, br, etc.)
    #
    active_shard_url = (
        f"https://americas.api.riotgames.com/riot/account/v1/"
        f"active-shards/by-game/val/by-puuid/{puuid}"
    )
    try:
        resp = requests.get(active_shard_url, headers=headers)
        resp.raise_for_status()
        active_shard_data = resp.json()
        actual_region = active_shard_data["activeShard"]  # e.g. "na", "eu", "ap", "kr"
        print("ACTIVE SHARD:", actual_region)
    except Exception as e:
        print(f"Error fetching active shard: {e}")
        return

    #
    # 3) Map that region to the correct subdomain for Valorant's Match-V1
    #
    region_map = {
        "na": "americas.api.riotgames.com",
        "latam": "americas.api.riotgames.com",
        "br": "americas.api.riotgames.com",
        "eu": "eu.api.riotgames.com",
        "ap": "asia.api.riotgames.com",
        "kr": "kr.api.riotgames.com"
    }

    val_domain = region_map.get(actual_region, "americas.api.riotgames.com")
    if val_domain != "americas.api.riotgames.com" and actual_region not in region_map:
        print(f"Unknown activeShard '{actual_region}', defaulting to americas.")

    #
    # 4) Fetch last 5 matches from VAL-MATCH-V1 on the correct shard
    #
    match_history_url = f"https://{val_domain}/val/match/v1/matchlists/by-puuid/{puuid}"
    try:
        r = requests.get(match_history_url, headers=headers)
        r.raise_for_status()
        data = r.json()
        matches = data.get("history", [])[:5]  # last 5 matches
    except Exception as e:
        print(f"Error fetching match history: {e}")
        return

    if not matches:
        print("No matches found.")
        return

    #
    # 5) Iterate over each match, sum up kills/deaths/assists, and check if won
    #
    total_kills = total_deaths = total_assists = total_wins = 0

    for match_item in matches:
        match_id = match_item["matchId"]
        match_url = f"https://{val_domain}/val/match/v1/matches/{match_id}"

        try:
            resp = requests.get(match_url, headers=headers)
            resp.raise_for_status()
            match_data = resp.json()
        except Exception as e:
            print(f"Skipping match {match_id} due to error: {e}")
            continue

        # Depending on the actual JSON, we look for match_data["players"]
        players_list = match_data.get("players", [])
        if not players_list:
            # Sometimes data might be under different structure. If so, print for debugging:
            # print(match_data)
            continue

        # Find the player object that matches our puuid
        player_data = next((p for p in players_list if p["puuid"] == puuid), None)
        if not player_data:
            continue

        # Extract K/D/A from the player's "stats" object
        stats = player_data.get("stats", {})
        kills = stats.get("kills", 0)
        deaths = stats.get("deaths", 0)
        assists = stats.get("assists", 0)

        total_kills += kills
        total_deaths += deaths
        total_assists += assists

        # Check if their team won
        team_id = player_data.get("teamId")
        teams_data = match_data.get("teams", {})

        # Example teams_data structure is often like:
        # {"Red": {"won": true, ...}, "Blue": {"won": false, ...}}
        # If team_id is "Red" or "Blue", we can check teams_data[team_id]["won"]
        if team_id and team_id in teams_data:
            if teams_data[team_id].get("won"):
                total_wins += 1

    #
    # 6) Compute KDA and Win Rate
    #
    deaths_safe = max(1, total_deaths)  # avoid dividing by zero
    kda = (total_kills + total_assists) / deaths_safe
    games_count = len(matches)
    win_rate = (total_wins / games_count) * 100 if games_count else 0

    #
    # 7) Print Results
    #
    print(f"\nStats for {riot_id}:")
    print(f"KDA: {kda:.2f}")
    print(f"Win Rate: {win_rate:.1f}%")

if __name__ == "__main__":
    main()
