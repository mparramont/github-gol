#!/usr/bin/env python3
"""Visualize the current GitHub contribution calendar as a grid matching the GOL layout."""

import subprocess
import json
import sys


def main() -> None:
    result = subprocess.run(
        [
            "gh",
            "api",
            "graphql",
            "-f",
            'query=query { user(login: "mparramont") { contributionsCollection { contributionCalendar { weeks { contributionDays { date contributionCount } } } } } }',
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Error calling GitHub GraphQL API: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    try:
        data = json.loads(result.stdout)
        weeks = data["data"]["user"]["contributionsCollection"]["contributionCalendar"][
            "weeks"
        ]
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(
            f"Error parsing API response: {e}\nResponse: {result.stdout}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Build 52x7 grid (most recent 52 weeks)
    # Take last 53 weeks and trim to 52 complete + current
    grid = []
    for row in range(7):  # Sunday=0 to Saturday=6
        line = ""
        for week in weeks[-52:]:
            days = week["contributionDays"]
            if row < len(days):
                count = days[row]["contributionCount"]
                if count == 0:
                    line += "."
                elif count <= 3:
                    line += "░"
                elif count <= 6:
                    line += "▒"
                elif count <= 10:
                    line += "▓"
                else:
                    line += "█"
            else:
                line += " "
        grid.append(line)

    print("GitHub Contributions Calendar (last 52 weeks):")
    print("Week:  " + "".join([str(i % 10) for i in range(52)]))
    day_names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    for i, line in enumerate(grid):
        print(f"{day_names[i]}: {line}")

    # Show GOL-specific dates
    print("\nRecent pixel commit dates (looking for GOL pattern):")
    for week in weeks[-10:]:
        for day in week["contributionDays"]:
            if day["contributionCount"] > 0:
                print(f"  {day['date']}: {day['contributionCount']} contributions")


if __name__ == "__main__":
    main()
