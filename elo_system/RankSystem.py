class Rank:
    def __init__(
        self, 
        rank_name: str, 
        pts_threshold: int, 
        lose_minus: int, 
        win_plus: int, 
        ws_bonus: int, 
        wins_needed: int, 
    ):
        self.rank_name = rank_name
        self.pts_threshold = pts_threshold
        self.lose_minus = lose_minus
        self.win_plus = win_plus
        self.ws_bonus = ws_bonus
        self.wins_needed = wins_needed

    def __repr__(self):
        return (
            f"Rank: {self.rank_name}, "
            f"Points Threshold: {self.pts_threshold}, "
            f"Lose Penalty: {self.lose_minus}, "
            f"Win Reward: {self.win_plus}, "
            f"Win Streak Bonus: {self.ws_bonus}, "
            f"Wins Needed: {self.wins_needed}, "
        )


class RankSystem:
    def __init__(self):
        self.ranks = []

        # Define rank settings
        rank_definitions = [
            ("Bronze 1", 0, -1, 20, 3, 1),
            ("Bronze 2", 50, -2, 19, 3, 1),
            ("Bronze 3", 100, -3, 18, 3, 1),
            ("Bronze 4", 150, -4, 17, 3, 1),
            ("Bronze 5", 200, -5, 16, 3, 1),
            ("Silver 1", 250, -6, 15, 2, 2),
            ("Silver 2", 300, -7, 14, 2, 2),
            ("Silver 3", 350, -8, 13, 2, 2, ),
            ("Silver 4", 400, -9, 12, 2, 2),
            ("Silver 5", 450, -10, 11, 2, 2),
            ("Gold 1", 500, -10, 10, 1, 3,),
            ("Gold 2", 550, -10, 9, 1, 3,),
            ("Gold 3", 600, -10, 8, 1, 3,),
            ("Gold 4", 650, -10, 7, 1, 3,),
            ("Gold 5", 700, -10, 6, 1, 3),
            ("Master 1", 750, -10, 5, 1, 3),
            ("Master 2", 800, -10, 4, 1, 3),
            ("Master 3", 850, -10, 3, 1, 3),
            ("Master 4", 900, -10, 2, 1, 3),
            ("Master 5", 950, -10, 1, 1, 3),
            ("Champion", 1000, -10, 10, 0, 0),
        ]

        for rank_name, pts_threshold, lose_minus, win_plus, streak_bonus, wins_needed in rank_definitions:
            self.ranks.append(
                Rank(rank_name, pts_threshold, lose_minus, win_plus, streak_bonus, wins_needed)
            )

    def get_rank_by_points(self, points: int) -> Rank:
        """Find the appropriate rank based on points."""
        for rank in reversed(self.ranks):
            if points >= rank.pts_threshold:
                return rank
        return self.ranks[0]
            
if __name__ == "__main__":
    rankSystem = RankSystem()
    print(rankSystem.get_rank_by_points(points=0))
