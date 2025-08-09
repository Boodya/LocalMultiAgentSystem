import pygame
import sys
import random

# Initialize pygame
pygame.init()

# Constants
WIDTH, HEIGHT = 640, 480
CELL_SIZE = 20
ROWS, COLS = HEIGHT // CELL_SIZE, WIDTH // CELL_SIZE
SNAKE_COLOR = (0, 255, 0)
FOOD_COLOR = (255, 0, 0)
BG_COLOR = (0, 0, 0)
FPS = 10

# Directions
UP = (0, -1)
DOWN = (0, 1)
LEFT = (-1, 0)
RIGHT = (1, 0)

# Helper functions

def draw_cell(surface, color, pos):
    rect = pygame.Rect(pos[0]*CELL_SIZE, pos[1]*CELL_SIZE, CELL_SIZE, CELL_SIZE)
    pygame.draw.rect(surface, color, rect)


def random_food_position(snake):
    while True:
        pos = (random.randint(0, COLS-1), random.randint(0, ROWS-1))
        if pos not in snake:
            return pos


def main():
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Snake Game")
    clock = pygame.time.Clock()

    snake = [(COLS//2, ROWS//2)]
    direction = RIGHT
    food = random_food_position(snake)
    score = 0

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_UP and direction != DOWN:
                    direction = UP
                elif event.key == pygame.K_DOWN and direction != UP:
                    direction = DOWN
                elif event.key == pygame.K_LEFT and direction != RIGHT:
                    direction = LEFT
                elif event.key == pygame.K_RIGHT and direction != LEFT:
                    direction = RIGHT

        # Move snake
        new_head = ((snake[0][0] + direction[0]) % COLS, (snake[0][1] + direction[1]) % ROWS)
        if new_head in snake:
            print(f"Game over! Final score: {score}")
            running = False
            continue
        snake.insert(0, new_head)
        if new_head == food:
            score += 1
            food = random_food_position(snake)
        else:
            snake.pop()

        # Draw
        screen.fill(BG_COLOR)
        draw_cell(screen, FOOD_COLOR, food)
        for segment in snake:
            draw_cell(screen, SNAKE_COLOR, segment)
        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()
