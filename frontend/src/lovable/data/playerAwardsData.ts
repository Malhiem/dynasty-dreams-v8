// @ts-nocheck
// Shared player awards & all-star data used across League History and Player Card

export interface AllStarPlayer {
  player: string;
  position: "C" | "LW" | "RW" | "D" | "G";
  team: string;
  fantasyPoints: number;
}

export interface AllStarSeason {
  season: string;
  firstTeam: AllStarPlayer[];
  secondTeam: AllStarPlayer[];
}

export const allStarTeams: AllStarSeason[] = [
  {
    season: "2025-26",
    firstTeam: [
      { player: "Connor McDavid", position: "C", team: "Team Frostbite", fantasyPoints: 648 },
      { player: "Artemi Panarin", position: "LW", team: "Polar Dynasty", fantasyPoints: 512 },
      { player: "Nikita Kucherov", position: "RW", team: "Ice Wolves", fantasyPoints: 578 },
      { player: "Cale Makar", position: "D", team: "Team Frostbite", fantasyPoints: 478 },
      { player: "Quinn Hughes", position: "D", team: "Blizzard Force", fantasyPoints: 442 },
      { player: "Connor Hellebuyck", position: "G", team: "Arctic Thunder", fantasyPoints: 312 },
    ],
    secondTeam: [
      { player: "Nathan MacKinnon", position: "C", team: "Polar Dynasty", fantasyPoints: 601 },
      { player: "Kirill Kaprizov", position: "LW", team: "Glacier Kings", fantasyPoints: 489 },
      { player: "David Pastrnak", position: "RW", team: "Arctic Thunder", fantasyPoints: 534 },
      { player: "Adam Fox", position: "D", team: "Frozen Elite", fantasyPoints: 421 },
      { player: "Roman Josi", position: "D", team: "Tundra Titans", fantasyPoints: 398 },
      { player: "Igor Shesterkin", position: "G", team: "Frozen Elite", fantasyPoints: 289 },
    ],
  },
  {
    season: "2024-25",
    firstTeam: [
      { player: "Nathan MacKinnon", position: "C", team: "Polar Dynasty", fantasyPoints: 612 },
      { player: "Kirill Kaprizov", position: "LW", team: "Glacier Kings", fantasyPoints: 512 },
      { player: "Nikita Kucherov", position: "RW", team: "Ice Wolves", fantasyPoints: 567 },
      { player: "Cale Makar", position: "D", team: "Team Frostbite", fantasyPoints: 521 },
      { player: "Adam Fox", position: "D", team: "Frozen Elite", fantasyPoints: 456 },
      { player: "Igor Shesterkin", position: "G", team: "Frozen Elite", fantasyPoints: 345 },
    ],
    secondTeam: [
      { player: "Connor McDavid", position: "C", team: "Team Frostbite", fantasyPoints: 598 },
      { player: "Artemi Panarin", position: "LW", team: "Polar Dynasty", fantasyPoints: 478 },
      { player: "David Pastrnak", position: "RW", team: "Arctic Thunder", fantasyPoints: 512 },
      { player: "Quinn Hughes", position: "D", team: "Blizzard Force", fantasyPoints: 432 },
      { player: "Roman Josi", position: "D", team: "Tundra Titans", fantasyPoints: 389 },
      { player: "Connor Hellebuyck", position: "G", team: "Arctic Thunder", fantasyPoints: 298 },
    ],
  },
  {
    season: "2023-24",
    firstTeam: [
      { player: "Connor McDavid", position: "C", team: "Team Frostbite", fantasyPoints: 634 },
      { player: "Artemi Panarin", position: "LW", team: "Polar Dynasty", fantasyPoints: 498 },
      { player: "Nikita Kucherov", position: "RW", team: "Ice Wolves", fantasyPoints: 598 },
      { player: "Quinn Hughes", position: "D", team: "Blizzard Force", fantasyPoints: 462 },
      { player: "Cale Makar", position: "D", team: "Team Frostbite", fantasyPoints: 445 },
      { player: "Connor Hellebuyck", position: "G", team: "Arctic Thunder", fantasyPoints: 298 },
    ],
    secondTeam: [
      { player: "Leon Draisaitl", position: "C", team: "Glacier Kings", fantasyPoints: 578 },
      { player: "Kirill Kaprizov", position: "LW", team: "Glacier Kings", fantasyPoints: 467 },
      { player: "David Pastrnak", position: "RW", team: "Arctic Thunder", fantasyPoints: 498 },
      { player: "Adam Fox", position: "D", team: "Frozen Elite", fantasyPoints: 434 },
      { player: "Erik Karlsson", position: "D", team: "Snow Storm", fantasyPoints: 412 },
      { player: "Andrei Vasilevskiy", position: "G", team: "Ice Wolves", fantasyPoints: 278 },
    ],
  },
  {
    season: "2022-23",
    firstTeam: [
      { player: "Connor McDavid", position: "C", team: "Team Frostbite", fantasyPoints: 621 },
      { player: "Artemi Panarin", position: "LW", team: "Polar Dynasty", fantasyPoints: 476 },
      { player: "Mitch Marner", position: "RW", team: "Snow Storm", fantasyPoints: 445 },
      { player: "Erik Karlsson", position: "D", team: "Snow Storm", fantasyPoints: 489 },
      { player: "Cale Makar", position: "D", team: "Team Frostbite", fantasyPoints: 456 },
      { player: "Linus Ullmark", position: "G", team: "Snow Storm", fantasyPoints: 289 },
    ],
    secondTeam: [
      { player: "Nathan MacKinnon", position: "C", team: "Polar Dynasty", fantasyPoints: 589 },
      { player: "Kirill Kaprizov", position: "LW", team: "Glacier Kings", fantasyPoints: 434 },
      { player: "David Pastrnak", position: "RW", team: "Arctic Thunder", fantasyPoints: 423 },
      { player: "Quinn Hughes", position: "D", team: "Blizzard Force", fantasyPoints: 412 },
      { player: "Adam Fox", position: "D", team: "Frozen Elite", fantasyPoints: 398 },
      { player: "Igor Shesterkin", position: "G", team: "Frozen Elite", fantasyPoints: 267 },
    ],
  },
  {
    season: "2021-22",
    firstTeam: [
      { player: "Leon Draisaitl", position: "C", team: "Glacier Kings", fantasyPoints: 578 },
      { player: "Kirill Kaprizov", position: "LW", team: "Glacier Kings", fantasyPoints: 456 },
      { player: "Nikita Kucherov", position: "RW", team: "Ice Wolves", fantasyPoints: 523 },
      { player: "Cale Makar", position: "D", team: "Team Frostbite", fantasyPoints: 498 },
      { player: "Roman Josi", position: "D", team: "Tundra Titans", fantasyPoints: 412 },
      { player: "Igor Shesterkin", position: "G", team: "Frozen Elite", fantasyPoints: 324 },
    ],
    secondTeam: [
      { player: "Auston Matthews", position: "C", team: "Arctic Thunder", fantasyPoints: 534 },
      { player: "Artemi Panarin", position: "LW", team: "Polar Dynasty", fantasyPoints: 423 },
      { player: "David Pastrnak", position: "RW", team: "Arctic Thunder", fantasyPoints: 467 },
      { player: "Adam Fox", position: "D", team: "Frozen Elite", fantasyPoints: 389 },
      { player: "Quinn Hughes", position: "D", team: "Blizzard Force", fantasyPoints: 378 },
      { player: "Andrei Vasilevskiy", position: "G", team: "Ice Wolves", fantasyPoints: 298 },
    ],
  },
  {
    season: "2020-21",
    firstTeam: [
      { player: "Auston Matthews", position: "C", team: "Arctic Thunder", fantasyPoints: 556 },
      { player: "Artemi Panarin", position: "LW", team: "Polar Dynasty", fantasyPoints: 445 },
      { player: "Nikita Kucherov", position: "RW", team: "Ice Wolves", fantasyPoints: 512 },
      { player: "Adam Fox", position: "D", team: "Frozen Elite", fantasyPoints: 445 },
      { player: "Roman Josi", position: "D", team: "Tundra Titans", fantasyPoints: 398 },
      { player: "Andrei Vasilevskiy", position: "G", team: "Ice Wolves", fantasyPoints: 298 },
    ],
    secondTeam: [
      { player: "Connor McDavid", position: "C", team: "Team Frostbite", fantasyPoints: 534 },
      { player: "Kirill Kaprizov", position: "LW", team: "Glacier Kings", fantasyPoints: 412 },
      { player: "Mitch Marner", position: "RW", team: "Snow Storm", fantasyPoints: 423 },
      { player: "Cale Makar", position: "D", team: "Team Frostbite", fantasyPoints: 412 },
      { player: "Erik Karlsson", position: "D", team: "Snow Storm", fantasyPoints: 378 },
      { player: "Connor Hellebuyck", position: "G", team: "Arctic Thunder", fantasyPoints: 278 },
    ],
  },
  {
    season: "2019-20",
    firstTeam: [
      { player: "Leon Draisaitl", position: "C", team: "Glacier Kings", fantasyPoints: 542 },
      { player: "Artemi Panarin", position: "LW", team: "Polar Dynasty", fantasyPoints: 467 },
      { player: "David Pastrnak", position: "RW", team: "Arctic Thunder", fantasyPoints: 489 },
      { player: "Roman Josi", position: "D", team: "Tundra Titans", fantasyPoints: 432 },
      { player: "Cale Makar", position: "D", team: "Team Frostbite", fantasyPoints: 398 },
      { player: "Connor Hellebuyck", position: "G", team: "Arctic Thunder", fantasyPoints: 278 },
    ],
    secondTeam: [
      { player: "Nathan MacKinnon", position: "C", team: "Polar Dynasty", fantasyPoints: 512 },
      { player: "Kirill Kaprizov", position: "LW", team: "Glacier Kings", fantasyPoints: 389 },
      { player: "Nikita Kucherov", position: "RW", team: "Ice Wolves", fantasyPoints: 456 },
      { player: "Adam Fox", position: "D", team: "Frozen Elite", fantasyPoints: 378 },
      { player: "Quinn Hughes", position: "D", team: "Blizzard Force", fantasyPoints: 356 },
      { player: "Andrei Vasilevskiy", position: "G", team: "Ice Wolves", fantasyPoints: 265 },
    ],
  },
  {
    season: "2018-19",
    firstTeam: [
      { player: "Nikita Kucherov", position: "RW", team: "Ice Wolves", fantasyPoints: 538 },
      { player: "Artemi Panarin", position: "LW", team: "Polar Dynasty", fantasyPoints: 434 },
      { player: "Connor McDavid", position: "C", team: "Team Frostbite", fantasyPoints: 521 },
      { player: "Brent Burns", position: "D", team: "Polar Dynasty", fantasyPoints: 418 },
      { player: "Roman Josi", position: "D", team: "Tundra Titans", fantasyPoints: 389 },
      { player: "Andrei Vasilevskiy", position: "G", team: "Ice Wolves", fantasyPoints: 265 },
    ],
    secondTeam: [
      { player: "Leon Draisaitl", position: "C", team: "Glacier Kings", fantasyPoints: 498 },
      { player: "Kirill Kaprizov", position: "LW", team: "Glacier Kings", fantasyPoints: 378 },
      { player: "David Pastrnak", position: "RW", team: "Arctic Thunder", fantasyPoints: 445 },
      { player: "Cale Makar", position: "D", team: "Team Frostbite", fantasyPoints: 367 },
      { player: "Adam Fox", position: "D", team: "Frozen Elite", fantasyPoints: 345 },
      { player: "Connor Hellebuyck", position: "G", team: "Arctic Thunder", fantasyPoints: 245 },
    ],
  },
];

// Award winners data (without JSX, shared across components)
export interface AwardWinnerEntry {
  season: string;
  player: string;
  position: string;
  team: string;
  fantasyPoints: number;
}

export interface AwardData {
  name: string;
  description: string;
  winners: AwardWinnerEntry[];
}

export const awardWinnersData: AwardData[] = [
  {
    name: "Art Ross Trophy",
    description: "Season MVP — most fantasy points in the regular season",
    winners: [
      { season: "2025-26", player: "Connor McDavid", position: "C", team: "Team Frostbite", fantasyPoints: 648 },
      { season: "2024-25", player: "Nathan MacKinnon", position: "C", team: "Polar Dynasty", fantasyPoints: 612 },
      { season: "2023-24", player: "Connor McDavid", position: "C", team: "Team Frostbite", fantasyPoints: 634 },
      { season: "2022-23", player: "Connor McDavid", position: "C", team: "Team Frostbite", fantasyPoints: 621 },
      { season: "2021-22", player: "Leon Draisaitl", position: "C", team: "Glacier Kings", fantasyPoints: 578 },
      { season: "2020-21", player: "Auston Matthews", position: "C", team: "Arctic Thunder", fantasyPoints: 556 },
      { season: "2019-20", player: "Leon Draisaitl", position: "C", team: "Glacier Kings", fantasyPoints: 542 },
      { season: "2018-19", player: "Nikita Kucherov", position: "RW", team: "Ice Wolves", fantasyPoints: 538 },
    ],
  },
  {
    name: "Conn Smythe Trophy",
    description: "Playoff MVP",
    winners: [
      { season: "2025-26", player: "Nathan MacKinnon", position: "C", team: "Polar Dynasty", fantasyPoints: 189 },
      { season: "2024-25", player: "Connor McDavid", position: "C", team: "Team Frostbite", fantasyPoints: 201 },
      { season: "2023-24", player: "Nikita Kucherov", position: "RW", team: "Ice Wolves", fantasyPoints: 178 },
      { season: "2022-23", player: "Leon Draisaitl", position: "C", team: "Glacier Kings", fantasyPoints: 184 },
      { season: "2021-22", player: "Cale Makar", position: "D", team: "Team Frostbite", fantasyPoints: 162 },
      { season: "2020-21", player: "Andrei Vasilevskiy", position: "G", team: "Ice Wolves", fantasyPoints: 148 },
      { season: "2019-20", player: "Nathan MacKinnon", position: "C", team: "Polar Dynasty", fantasyPoints: 172 },
      { season: "2018-19", player: "Ryan O'Reilly", position: "C", team: "Arctic Thunder", fantasyPoints: 145 },
    ],
  },
  {
    name: "Hart Trophy",
    description: "Best forward",
    winners: [
      { season: "2025-26", player: "Connor McDavid", position: "C", team: "Team Frostbite", fantasyPoints: 648 },
      { season: "2024-25", player: "Nathan MacKinnon", position: "C", team: "Polar Dynasty", fantasyPoints: 612 },
      { season: "2023-24", player: "Nikita Kucherov", position: "RW", team: "Ice Wolves", fantasyPoints: 598 },
      { season: "2022-23", player: "Connor McDavid", position: "C", team: "Team Frostbite", fantasyPoints: 621 },
      { season: "2021-22", player: "Auston Matthews", position: "C", team: "Arctic Thunder", fantasyPoints: 534 },
      { season: "2020-21", player: "Auston Matthews", position: "C", team: "Arctic Thunder", fantasyPoints: 556 },
      { season: "2019-20", player: "Leon Draisaitl", position: "C", team: "Glacier Kings", fantasyPoints: 542 },
      { season: "2018-19", player: "Nikita Kucherov", position: "RW", team: "Ice Wolves", fantasyPoints: 538 },
    ],
  },
  {
    name: "Norris Trophy",
    description: "Best defenseman",
    winners: [
      { season: "2025-26", player: "Cale Makar", position: "D", team: "Team Frostbite", fantasyPoints: 478 },
      { season: "2024-25", player: "Cale Makar", position: "D", team: "Team Frostbite", fantasyPoints: 521 },
      { season: "2023-24", player: "Quinn Hughes", position: "D", team: "Blizzard Force", fantasyPoints: 462 },
      { season: "2022-23", player: "Erik Karlsson", position: "D", team: "Snow Storm", fantasyPoints: 489 },
      { season: "2021-22", player: "Cale Makar", position: "D", team: "Team Frostbite", fantasyPoints: 498 },
      { season: "2020-21", player: "Adam Fox", position: "D", team: "Frozen Elite", fantasyPoints: 445 },
      { season: "2019-20", player: "Roman Josi", position: "D", team: "Tundra Titans", fantasyPoints: 432 },
      { season: "2018-19", player: "Brent Burns", position: "D", team: "Polar Dynasty", fantasyPoints: 418 },
    ],
  },
  {
    name: "Vezina Trophy",
    description: "Best goalie",
    winners: [
      { season: "2025-26", player: "Connor Hellebuyck", position: "G", team: "Arctic Thunder", fantasyPoints: 312 },
      { season: "2024-25", player: "Igor Shesterkin", position: "G", team: "Frozen Elite", fantasyPoints: 345 },
      { season: "2023-24", player: "Connor Hellebuyck", position: "G", team: "Arctic Thunder", fantasyPoints: 298 },
      { season: "2022-23", player: "Linus Ullmark", position: "G", team: "Snow Storm", fantasyPoints: 289 },
      { season: "2021-22", player: "Igor Shesterkin", position: "G", team: "Frozen Elite", fantasyPoints: 324 },
      { season: "2020-21", player: "Andrei Vasilevskiy", position: "G", team: "Ice Wolves", fantasyPoints: 298 },
      { season: "2019-20", player: "Connor Hellebuyck", position: "G", team: "Arctic Thunder", fantasyPoints: 278 },
      { season: "2018-19", player: "Andrei Vasilevskiy", position: "G", team: "Ice Wolves", fantasyPoints: 265 },
    ],
  },
];

// Helper: build a map of player name → list of accolades
export interface PlayerAccolade {
  type: string;
  emoji: string;
  count: number;
}

export function getPlayerAccolades(playerName: string, awards: { name: string; winners: { player: string }[] }[]): PlayerAccolade[] {
  const accolades: PlayerAccolade[] = [];

  // Individual awards
  const awardEmojis: Record<string, string> = {
    "Art Ross Trophy": "🏆",
    "Conn Smythe Trophy": "⭐",
    "Hart Trophy": "🎖️",
    "Norris Trophy": "🛡️",
    "Vezina Trophy": "🥇",
  };

  for (const award of awards) {
    const count = award.winners.filter(w => w.player === playerName).length;
    if (count > 0) {
      accolades.push({ type: award.name, emoji: awardEmojis[award.name] || "🏅", count });
    }
  }

  // All-Star selections
  let firstTeamCount = 0;
  let secondTeamCount = 0;
  for (const season of allStarTeams) {
    if (season.firstTeam.some(p => p.player === playerName)) firstTeamCount++;
    if (season.secondTeam.some(p => p.player === playerName)) secondTeamCount++;
  }
  if (firstTeamCount > 0) {
    accolades.push({ type: "1st Team All-Star", emoji: "⭐", count: firstTeamCount });
  }
  if (secondTeamCount > 0) {
    accolades.push({ type: "2nd Team All-Star", emoji: "✨", count: secondTeamCount });
  }

  return accolades;
}
