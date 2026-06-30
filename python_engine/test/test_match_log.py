"""对局测试：打印双方每一步操作、board 完整状态、手牌"""

import asyncio
import json
import sys
import logging

sys.path.insert(0, ".")

from python_engine import GameEngine, Faction

# 设置日志级别为 INFO，确保看到所有操作和状态
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)-7s %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)


def print_hand(player):
    """打印玩家手牌"""
    cards = [f"{c.name}({c.definition.base_strength})" for c in player.hand.cards]
    print(f"  🃏 {player.name} Hand ({len(cards)}): [{', '.join(cards)}]")


def print_board(engine):
    """打印完整 board 状态"""
    print(engine.board.dump_state())


async def run_matchup(deck_index_1: int, deck_index_2: int):
    """运行一场对局并打印详细日志"""
    with open("python_engine/decks.json") as f:
        decks = json.load(f)

    faction_map = {
        "realms": Faction.NORTHERN_REALMS,
        "nilfgaard": Faction.NILFGAARD,
        "monsters": Faction.MONSTERS,
        "scoiatael": Faction.SCOIATAEL,
        "skellige": Faction.SKELLIGE,
    }

    p1_deck = decks[deck_index_1]
    p2_deck = decks[deck_index_2]

    engine = GameEngine("python_engine/cards.json")
    engine.setup_game(
        faction_map[p1_deck["faction"]],
        faction_map[p2_deck["faction"]],
        player1_deck_ids=[tuple(c) for c in p1_deck["cards"]],
        player1_leader_id=p1_deck.get("leader"),
        player2_deck_ids=[tuple(c) for c in p2_deck["cards"]],
        player2_leader_id=p2_deck.get("leader"),
    )

    print("=" * 80)
    print(f"🎮 Matchup: Deck#{deck_index_1} ({p1_deck['faction']}) vs Deck#{deck_index_2} ({p2_deck['faction']})")
    print("=" * 80)

    await engine.start_game()

    print("\n📍 After initial redraw:")
    print_hand(engine.game_state.player1)
    print_hand(engine.game_state.player2)
    print_board(engine)

    round_num = 0
    while engine.game_state.is_playing:
        round_num += 1
        print(f"\n{'='*80}")
        print(f"🔵 ROUND {round_num} START")
        print(f"{'='*80}")
        print_hand(engine.game_state.player1)
        print_hand(engine.game_state.player2)
        print_board(engine)

        turn_count = 0
        max_turns = 50
        while turn_count < max_turns:
            current_player = engine.game_state.current_player
            opponent = current_player.opponent

            # 双方都 pass 则结束本轮
            if current_player.passed and opponent.passed:
                break

            # 如果当前玩家已 pass，切换到对手
            if current_player.passed:
                engine.game_state.current_player = opponent
                continue

            turn_count += 1
            action_desc = ""

            # AI 决策：有手牌且随机概率 > 0.15 时出牌，否则 pass
            if current_player.hand.cards and (turn_count % 3 != 0):
                card = current_player.hand.cards[0]  # 简单策略：出第一张
                await engine.play_card(current_player, card)
                action_desc = f"PLAY {card.name}"
            else:
                await engine.pass_round(current_player)
                action_desc = "PASS"

            print(f"\n  ▶ Turn {turn_count}: {current_player.name} → {action_desc}")
            print_hand(engine.game_state.player1)
            print_hand(engine.game_state.player2)
            print_board(engine)

            # 切换玩家
            engine.game_state.current_player = opponent

        # 确保双方都 pass
        if not engine.game_state.player1.passed:
            await engine.pass_round(engine.game_state.player1)
        if not engine.game_state.player2.passed:
            await engine.pass_round(engine.game_state.player2)

        print(f"\n🔴 ROUND {round_num} END")
        result = await engine.end_round()
        print(f"  Winner: {result.winner.name if result.winner else 'Draw'}")
        print(f"  P1 Score: {result.player1_score}, P2 Score: {result.player2_score}")
        print_board(engine)

    # 游戏结束
    winner = engine.get_game_winner()
    print(f"\n{'='*80}")
    print(f"🏆 GAME OVER — Winner: {winner.name if winner else 'Draw'}")
    print(f"{'='*80}")


if __name__ == "__main__":
    # 默认测试 matchup 0-1，可通过命令行参数指定
    idx1 = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    idx2 = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    asyncio.run(run_matchup(idx1, idx2))
