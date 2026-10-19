import itertools
import random
import unittest
from services.draft_salary import feasible_completion

def brute(slots,options,lower,upper):
    for selected in itertools.permutations(options,len(slots)):
        if all(slot in charges for slot,(_,charges) in zip(slots,selected)):
            cost=sum(charges[slot] for slot,(_,charges) in zip(slots,selected))
            if lower<=cost<=upper:return True
    return False

class LargeSalaryPool(unittest.TestCase):
    def test_final_slot_rejects_gap_in_10005_players_exactly(self):
        pool=[(str(i),{'ACT':100}) for i in range(10003)]+[('six',{'ACT':600}),('ten',{'ACT':1000})]
        self.assertIs(feasible_completion(('ACT',),pool,1300,1700),False)
        self.assertIs(feasible_completion(('ACT',),pool,400,800),True)
    def test_identical_players_remain_distinct_and_not_reusable(self):
        self.assertIs(feasible_completion(('C','RW'),[('one',{'C':100,'RW':100})],200,200),False)
        self.assertIs(feasible_completion(('C','RW'),[('one',{'C':100,'RW':100}),('two',{'C':100,'RW':100})],200,200),True)
    def test_large_equal_pool_finds_and_rejects_exact_completion(self):
        pool=[(str(i),{'C':100,'RW':100}) for i in range(10005)]
        self.assertIs(feasible_completion(('C','RW','RW'),pool,300,300),True)
        self.assertIs(feasible_completion(('C','RW','RW'),pool,301,400),False)
    def test_grouping_matches_independent_small_pool_enumeration(self):
        rng=random.Random(107)
        for _ in range(120):
            options=[(str(i),{slot:rng.choice([0,100,200]) for slot in ('C','RW') if rng.choice([True,True,False])}) for i in range(6)]
            slots=tuple(rng.choice(['C','RW']) for _ in range(3));lower=rng.choice([0,100,300,500]);upper=lower+rng.choice([0,100,200])
            self.assertEqual(feasible_completion(slots,options,lower,upper),brute(slots,options,lower,upper))
