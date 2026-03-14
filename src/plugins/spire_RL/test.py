from decapitate_the_spire import game as dg

def main():
    # Also consider dg.SimpleDungeon and dg.MiniDungeon for testing.
    game = dg.Game(dg.TheSilent, dg.Exordium)

    is_terminal = False
    while not is_terminal:
        # You'll be determining the actions; this is a placeholder. See the
        # wiki for details on the action space.
        action_0, action_1 = (0, 0)
        # This is the core gameplay loop.
        _, is_terminal, _ = game.step((action_0, action_1))
        print("Current state:", game.step)


if __name__ == "__main__":
    main()

