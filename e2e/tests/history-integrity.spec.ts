import { expect } from '@playwright/test';
import { ObjectId } from 'mongodb';
import { test } from '../support/h2h-cases';
import { database, result } from '../support/h2h';
import { historyFixture } from '../support/history-trophy-fixture';
import { HistoryTrophyPage } from '../pages/history-trophy/history-trophy.page';
test.setTimeout(45000);

test('INTEGRITY deleted franchise opens from lifetime history with saved records',async({page,api})=>{
  const l=await historyFixture(api),p=new HistoryTrophyPage(page);
  await database(db=>db.collection('teams').deleteOne({_id:new ObjectId(l.teams[0].id)}));
  await p.open(l.id,'/league-history');await p.ui.historyRow(l.teams[0].id).getByRole('link',{name:l.teams[0].name,exact:true}).click();
  await expect(p.ui.room()).toContainText('Archived franchise');await expect(p.ui.teamRafters()).toContainText(l.teams[0].name);
  await expect(p.ui.banner('championship',2026)).toBeVisible();await expect(p.ui.franchiseRecord(2026)).toBeVisible();
  expect((await p.ui.franchiseRecord(2026).getByRole('cell').allTextContents()).map(s=>s.trim())).toEqual(['1','8','2','2','1,000']);
});

test('INTEGRITY explicit champion ID overrides duplicate names and conflicting flags',async({page,api})=>{
  const l=await historyFixture(api),p=new HistoryTrophyPage(page);
  await database(async db=>{
    const snap=await db.collection('league_seasons').findOne({league_id:l.id,season_year:2026});if(!snap)throw Error('Missing snapshot');
    snap.teams[1].team_name=snap.teams[0].team_name;
    await db.collection('league_seasons').updateOne({_id:snap._id},{$set:{teams:snap.teams,champion_team_id:l.teams[1].id,champion_team_name:'Wrong name'}});
  });
  const league=await result(await api.get(`/api/leagues/${l.id}/trophy-room`));expect(league.seasons[0].champion.team_id).toBe(l.teams[1].id);
  await p.open(l.id,`/trophy-room/team/${l.teams[1].id}`);await p.year(2026);await expect(p.ui.banner('championship',2026)).toBeVisible();
  await p.open(l.id,`/trophy-room/team/${l.teams[0].id}`);await p.year(2026);await expect(p.ui.banner('championship',2026)).toHaveCount(0);
});

test('INTEGRITY tied awards and highest points display every holder',async({page,api})=>{
  const l=await historyFixture(api),p=new HistoryTrophyPage(page);
  await database(async db=>{
    const snap=await db.collection('league_seasons').findOne({league_id:l.id,season_year:2026});if(!snap)throw Error('Missing snapshot');
    snap.teams[0].points_for=2000;snap.teams[1].points_for=2000;
    snap.players.find((x:any)=>x.player_id===l.teams[1].players[0]).season_stats.points=100;
    await db.collection('league_seasons').updateOne({_id:snap._id},{$set:{teams:snap.teams,players:snap.players}});
  });
  await p.open(l.id,'/trophy-room');await p.year(2026);await expect(p.ui.banner('presidents_trophy',2026)).toHaveCount(2);await expect(p.ui.trophy('season-mvp',2026)).toHaveCount(2);
  await p.open(l.id,'/league-history');await p.ui.tab('League Records').click();for(const team of l.teams.slice(0,2))await expect(p.ui.pointsHolder(team.id,2026)).toBeVisible();
  for(const team of l.teams.slice(0,2)) {await p.open(l.id,`/trophy-room/team/${team.id}`);await p.year(2026);await expect(p.ui.banner('presidents_trophy',2026)).toBeVisible();await expect(p.ui.trophy('season-mvp',2026)).toBeVisible();}
});

test('INTEGRITY duplicate player names keep separate award count leaders',async({page,api})=>{
  const l=await historyFixture(api),p=new HistoryTrophyPage(page),a=l.teams[0].players[0],b=l.teams[1].players[0];
  await database(async db=>{
    const snaps=await db.collection('league_seasons').find({league_id:l.id}).sort({season_year:-1}).toArray();
    for(const [i,snap] of snaps.entries()) {
      for(const player of snap.players) if(player.player_id===a||player.player_id===b){player.name='Same player name';player.season_stats.points=player.player_id===(i<2?a:b)?110:80;}
      await db.collection('league_seasons').updateOne({_id:snap._id},{$set:{players:snap.players}});
    }
    await db.collection('players').updateOne({_id:new ObjectId(a)},{$set:{name:'Renamed live player'}});
  });
  await p.open(l.id,'/league-history');await p.ui.tab('Player Awards').click();
  await expect(p.ui.awardCount(a)).toContainText('Same player name — 2× winner');await expect(p.ui.awardCount(b)).toContainText('Same player name — 2× winner');
  await expect(p.ui.mvpAwardCard()).not.toContainText('4× winner');await expect(p.ui.panel()).not.toContainText('Renamed live player');
});

test('INTEGRITY legacy Roto ranks disclose unavailable standings',async({page,api})=>{
  const l=await historyFixture(api,'rotisserie'),p=new HistoryTrophyPage(page);
  await database(db=>db.collection('league_seasons').updateMany({league_id:l.id},{$set:{scoring_format:'rotisserie'}}));
  await p.open(l.id,`/trophy-room/team/${l.teams[0].id}`);await expect(p.ui.franchiseRecord(2026)).toContainText('Unavailable (legacy standings not saved)');
});

test('INTEGRITY ambiguous legacy champion is disclosed without invented banner',async({page,api})=>{
  const l=await historyFixture(api),p=new HistoryTrophyPage(page);
  await database(async db=>{
    const snap=await db.collection('league_seasons').findOne({league_id:l.id,season_year:2026});if(!snap)throw Error('Missing snapshot');
    snap.teams[1].team_name=snap.teams[0].team_name;for(const team of snap.teams)team.awards.championship_won_at=null;
    await db.collection('league_seasons').updateOne({_id:snap._id},{$set:{teams:snap.teams}});
  });
  await p.open(l.id,'/trophy-room');await p.year(2026);await expect(p.ui.alert()).toContainText('ambiguous franchise names');await expect(p.ui.banner('championship',2026)).toHaveCount(0);
});
