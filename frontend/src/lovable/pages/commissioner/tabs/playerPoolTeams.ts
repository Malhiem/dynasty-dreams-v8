export const divisions = [
  {name:"Atlantic",conference:"east",teams:["TBL","FLA","BUF","DET","MTL","BOS","OTT","TOR"]},
  {name:"Metropolitan",conference:"east",teams:["NYR","PHI","WSH","NJD","CAR","NYI","PIT","CBJ"]},
  {name:"Central",conference:"west",teams:["COL","MIN","NSH","CHI","DAL","UTA","WPG","STL"]},
  {name:"Pacific",conference:"west",teams:["CGY","VGK","SEA","VAN","ANA","EDM","SJS","LAK"]},
];
export const allTeams = divisions.flatMap(d=>d.teams);
export const conferenceTeams = (side:string) => divisions.filter(d=>d.conference===side).flatMap(d=>d.teams);
