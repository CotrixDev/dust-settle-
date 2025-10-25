# imba_shooter_improved.py
import pygame
import random
import numpy as np
import math
import os

# --- Настройки ---
WIDTH, HEIGHT = 800, 600
FPS = 60

# скорости в пикселях/сек
PLAYER_SPEED = 350
BULLET_SPEED = 700
ENEMY_SPEED_MIN = 60
ENEMY_SPEED_MAX = 140
ENEMY_SPAWN_INTERVAL = 900  # мс
PLAYER_MAX_HEALTH = 10

FIRE_COOLDOWN = 250  # мс между выстрелами

pygame.init()
pygame.mixer.init()

screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("2D Shooter — Imba Edition")
clock = pygame.time.Clock()
font = pygame.font.SysFont(None, 28)
big_font = pygame.font.SysFont(None, 72, bold=True)

# --- звуки ---
def make_sound(frequency, duration, volume=0.5, decay=5, noise=False):
    sample_rate = 44100
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    wave = (np.sin(2 * np.pi * frequency * t) * np.exp(-decay * t) * 32767).astype(np.int16)
    if noise:
        wave = wave + (np.random.randn(len(t)) * 4000).astype(np.int16)
    wave = np.clip(wave, -32767, 32767).astype(np.int16)
    stereo = np.column_stack((wave, wave))
    try:
        s = pygame.sndarray.make_sound(stereo.copy())
        s.set_volume(volume)
        return s
    except Exception as e:
        # если не получилось — вернуть None
        return None

shoot_sound = make_sound(880, 0.08, volume=0.25)
explosion_sound = make_sound(120, 0.22, volume=0.45, decay=3, noise=True)
levelup_sound = make_sound(440, 0.35, volume=0.35)

# --- частицы ---
particles = []
def create_particles(x, y, color, amount=15):
    for _ in range(amount):
        particles.append({
            "x": x + random.uniform(-6,6),
            "y": y + random.uniform(-6,6),
            "vx": random.uniform(-150, 150) / 60.0,
            "vy": random.uniform(-300, -50) / 60.0,
            "life": random.randint(18, 36),
            "color": color,
            "size": random.randint(2,5)
        })

def update_particles(surface):
    for p in particles[:]:
        p["x"] += p["vx"]
        p["y"] += p["vy"]
        p["vy"] += 6/60.0  # gravity for particles
        p["life"] -= 1
        if p["life"] <= 0:
            particles.remove(p)
        else:
            pygame.draw.circle(surface, p["color"], (int(p["x"]), int(p["y"])), p["size"])

# --- спрайты ---
class Bullet(pygame.sprite.Sprite):
    def __init__(self, x, y, vx=0, vy=-BULLET_SPEED, damage=1.0, color=(255,220,0), friendly=True):
        super().__init__()
        self.radius = 4 if friendly else 5
        self.image = pygame.Surface((self.radius*2, self.radius*2), pygame.SRCALPHA)
        pygame.draw.circle(self.image, color, (self.radius, self.radius), self.radius)
        self.rect = self.image.get_rect(center=(x, y))
        self.vx = vx
        self.vy = vy
        self.damage = damage
        self.friendly = friendly

    def update(self, dt):
        # dt — секунды
        self.rect.x += int(self.vx * dt)
        self.rect.y += int(self.vy * dt)
        if (self.rect.bottom < 0 or self.rect.top > HEIGHT or
            self.rect.right < 0 or self.rect.left > WIDTH):
            self.kill()

class Enemy(pygame.sprite.Sprite):
    def __init__(self, size=40, speed=100, health=1):
        super().__init__()
        self.size = size
        self.image = pygame.Surface((self.size, self.size), pygame.SRCALPHA)
        pygame.draw.polygon(
            self.image,
            (200, 50, 50),
            [(self.size // 2, 0), (self.size, self.size // 3),
             (self.size * 3 // 4, self.size), (self.size // 4, self.size), (0, self.size // 3)]
        )
        self.rect = self.image.get_rect()
        self.rect.x = random.randint(0, WIDTH - self.rect.width)
        self.rect.y = -self.rect.height
        self.speed = speed
        self.health = health
        self.type = "basic"

    def update(self, dt):
        self.rect.y += int(self.speed * dt)
        if self.rect.top > HEIGHT:
            self.kill()

class ZigzagEnemy(Enemy):
    def __init__(self, amplitude=80, frequency=1.2, **kwargs):
        size = kwargs.pop("size", random.randint(24,48))
        speed = kwargs.pop("speed", random.uniform(ENEMY_SPEED_MIN, ENEMY_SPEED_MAX))
        super().__init__(size=size, speed=speed, health=1)
        self.type = "zigzag"
        self.spawn_x = self.rect.x
        self.t = 0.0
        self.amp = amplitude
        self.freq = frequency

    def update(self, dt):
        self.t += dt
        self.rect.x = int(self.spawn_x + math.sin(self.t * self.freq * 2*math.pi) * self.amp)
        self.rect.y += int(self.speed * dt)
        if self.rect.top > HEIGHT or self.rect.left > WIDTH or self.rect.right < 0:
            self.kill()

class ShooterEnemy(Enemy):
    def __init__(self, shoot_interval=1.2, **kwargs):
        size = kwargs.pop("size", random.randint(28,56))
        speed = kwargs.pop("speed", random.uniform(ENEMY_SPEED_MIN*0.6, ENEMY_SPEED_MIN*1.2))
        super().__init__(size=size, speed=speed, health=2)
        self.type = "shooter"
        self.shoot_interval = shoot_interval
        self.timer = random.uniform(0, self.shoot_interval)

    def update(self, dt):
        self.rect.y += int(self.speed * dt)
        self.timer += dt
        if self.timer >= self.shoot_interval:
            self.timer = 0
            # выстрел вниз (будем создавать в основной логике, потому что нужно знать игрока)
        if self.rect.top > HEIGHT:
            self.kill()

class KamikazeEnemy(Enemy):
    def __init__(self, target_ref, **kwargs):
        size = kwargs.pop("size", random.randint(20,36))
        speed = kwargs.pop("speed", random.uniform(ENEMY_SPEED_MIN*1.2, ENEMY_SPEED_MAX*1.6))
        super().__init__(size=size, speed=speed, health=1)
        self.type = "kamikaze"
        self.target = target_ref

    def update(self, dt):
        # самонаводится на игрока
        if self.target:
            tx = self.target.rect.centerx
            ty = self.target.rect.centery
            dx = tx - self.rect.centerx
            dy = ty - self.rect.centery
            dist = math.hypot(dx, dy) + 1e-6
            vx = (dx / dist) * self.speed
            vy = (dy / dist) * self.speed
            self.rect.x += int(vx * dt)
            self.rect.y += int(vy * dt)
        else:
            self.rect.y += int(self.speed * dt)
        if self.rect.top > HEIGHT or self.rect.left > WIDTH or self.rect.right < 0:
            self.kill()

class ShieldedEnemy(Enemy):
    def __init__(self, **kwargs):
        size = kwargs.pop("size", random.randint(36,64))
        speed = kwargs.pop("speed", random.uniform(ENEMY_SPEED_MIN*0.6, ENEMY_SPEED_MAX*0.9))
        super().__init__(size=size, speed=speed, health=3)
        self.type = "shielded"
        self.shield_color = (120, 180, 255)

    def update(self, dt):
        self.rect.y += int(self.speed * dt)
        if self.rect.top > HEIGHT:
            self.kill()

class Player(pygame.sprite.Sprite):
    def __init__(self):
        super().__init__()
        self.w, self.h = 48, 40
        self.image = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        pygame.draw.polygon(self.image, (50, 150, 255),
                            [(self.w // 2, 0), (self.w, self.h), (0, self.h)])
        self.rect = self.image.get_rect(center=(WIDTH // 2, HEIGHT - 80))
        self.speed = PLAYER_SPEED
        self.health = PLAYER_MAX_HEALTH // 2
        self.last_shot_time = 0
        self.fire_cooldown = FIRE_COOLDOWN
        self.weapon = "pistol"

    def update(self, dt, keys):
        dx, dy = 0, 0
        if keys[pygame.K_LEFT] or keys[pygame.K_a]: dx -= 1
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]: dx += 1
        if keys[pygame.K_UP] or keys[pygame.K_w]: dy -= 1
        if keys[pygame.K_DOWN] or keys[pygame.K_s]: dy += 1
        if dx != 0 or dy != 0:
            norm = math.hypot(dx, dy) or 1
            self.rect.x += int((dx / norm) * self.speed * dt)
            self.rect.y += int((dy / norm) * self.speed * dt)
        self.rect.clamp_ip(screen.get_rect())

    def can_shoot(self, now_ms):
        return now_ms - self.last_shot_time >= self.fire_cooldown

    def shoot(self, bullets_group, now_ms):
        self.last_shot_time = now_ms
        if self.weapon == "pistol":
            bullets_group.add(Bullet(self.rect.centerx, self.rect.top - 8, vy=-BULLET_SPEED, damage=1.0))
            self.fire_cooldown = 250
        elif self.weapon == "sniper":
            bullets_group.add(Bullet(self.rect.centerx, self.rect.top - 8, vy=-BULLET_SPEED*1.6, damage=4.0, color=(0,255,0)))
            self.fire_cooldown = 600
        elif self.weapon == "shotgun":
            spread = [-0.18, -0.09, 0, 0.09, 0.18]  # angles in radians
            for a in spread:
                vx = math.sin(a) * BULLET_SPEED
                vy = -math.cos(a) * BULLET_SPEED
                bullets_group.add(Bullet(self.rect.centerx, self.rect.top - 8, vx=vx, vy=vy, damage=1.0, color=(255,180,100)))
            self.fire_cooldown = 700
        elif self.weapon == "ak":
            bullets_group.add(Bullet(self.rect.centerx, self.rect.top - 8, vy=-BULLET_SPEED, damage=0.6, color=(255,100,100)))
            self.fire_cooldown = 120
        if shoot_sound: shoot_sound.play()

# группы
player_group = pygame.sprite.GroupSingle()
bullets = pygame.sprite.Group()
enemies = pygame.sprite.Group()
enemy_bullets = pygame.sprite.Group()

player = Player()
player_group.add(player)

SPAWN_ENEMY = pygame.USEREVENT + 1
pygame.time.set_timer(SPAWN_ENEMY, ENEMY_SPAWN_INTERVAL)

score = 0
level = 1
running = True
game_over = False
choosing_weapon = False
enemy_size_boost = 1.0
enemy_speed_boost = 1.0
level_up_time = 0
LEVEL_UP_DURATION = 2000

def draw_hud():
    txt = font.render(f"Очки: {score}  |  Уровень: {level} | Оружие: {player.weapon}", True, (255, 255, 255))
    screen.blit(txt, (10, 10))
    hp_txt = font.render("Здоровье:", True, (255, 255, 255))
    screen.blit(hp_txt, (10, 36))
    for i in range(player.health):
        pygame.draw.rect(screen, (200, 50, 50), (120 + i * 22, 40, 18, 12))

def show_game_over():
    overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 180))
    screen.blit(overlay, (0, 0))
    text = big_font.render("ИГРА ОКОНЧЕНА", True, (255, 220, 220))
    sub = font.render(f"Очки: {score} — Нажмите R для рестарта", True, (255, 255, 255))
    screen.blit(text, text.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 30)))
    screen.blit(sub, sub.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 30)))

def show_weapon_choice():
    overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 200))
    screen.blit(overlay, (0, 0))

    title = big_font.render("Выберите оружие", True, (255, 255, 100))
    screen.blit(title, title.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 180)))

    options = [
        ("Снайпер", "1", (0, 255, 0)),
        ("Дробовик", "2", (255, 180, 50)),
        ("AK-47", "3", (255, 80, 80)),
    ]

    for i, (name, key, color) in enumerate(options):
        y = HEIGHT // 2 - 40 + i * 100
        label = font.render(f"{key} - {name}", True, (255, 255, 255))
        screen.blit(label, (WIDTH // 2 - 140, y))
        gun_rect = pygame.Rect(WIDTH // 2 + 20, y - 10, 100, 20)
        pygame.draw.rect(screen, color, gun_rect)
        # простые декорации для вида оружия
        if name == "Снайпер":
            pygame.draw.line(screen, (200, 200, 200), (gun_rect.right, gun_rect.centery),
                             (gun_rect.right + 40, gun_rect.centery), 3)
        elif name == "Дробовик":
            pygame.draw.rect(screen, (120, 70, 0), (gun_rect.x, gun_rect.y - 8, 20, 8))
        elif name == "AK-47":
            pygame.draw.rect(screen, (120, 70, 0), (gun_rect.x, gun_rect.y - 10, 25, 10))
            pygame.draw.rect(screen, (120, 70, 0), (gun_rect.centerx, gun_rect.bottom, 15, 20))

# вспомогательная генерация врагов (разновидности)
def spawn_enemy_by_type(level):
    r = random.random()
    # шанс появления более сложных врагов растёт с уровнем
    if r < 0.45:
        e = Enemy(size=int(random.randint(28,56) * enemy_size_boost),
                  speed=random.uniform(ENEMY_SPEED_MIN, ENEMY_SPEED_MAX) * enemy_speed_boost,
                  health=1)
    elif r < 0.7:
        e = ZigzagEnemy(amplitude=random.randint(40,110),
                        frequency=random.uniform(0.4,1.6),
                        size=random.randint(24,48),
                        speed=random.uniform(ENEMY_SPEED_MIN*0.9, ENEMY_SPEED_MAX*1.1) * enemy_speed_boost)
    elif r < 0.85:
        e = ShooterEnemy(shoot_interval=max(0.7, 1.2 - level*0.05),
                         size=random.randint(28,56),
                         speed=random.uniform(ENEMY_SPEED_MIN*0.6, ENEMY_SPEED_MIN*1.2) * enemy_speed_boost)
    elif r < 0.95:
        e = KamikazeEnemy(target_ref=player,
                          size=random.randint(20,36),
                          speed=random.uniform(ENEMY_SPEED_MIN*1.2, ENEMY_SPEED_MAX*1.7) * enemy_speed_boost)
    else:
        e = ShieldedEnemy(size=random.randint(36,64),
                          speed=random.uniform(ENEMY_SPEED_MIN*0.6, ENEMY_SPEED_MAX*0.9) * enemy_speed_boost)
    enemies.add(e)

# --- основной цикл ---
while running:
    ms = clock.tick(FPS)
    dt = ms / 1000.0  # секунды
    now = pygame.time.get_ticks()

    for event in pygame.event.get():
        if event.type == pygame.QUIT: running = False
        elif event.type == SPAWN_ENEMY and not (game_over or choosing_weapon):
            enemies_to_spawn = 1 + (level // 2)
            for _ in range(enemies_to_spawn):
                spawn_enemy_by_type(level)
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE: running = False
            if game_over and event.key == pygame.K_r:
                enemies.empty(); bullets.empty(); enemy_bullets.empty()
                player = Player(); player_group.add(player)
                score, level = 0, 1
                enemy_size_boost, enemy_speed_boost = 1.0, 1.0
                game_over = False
            if choosing_weapon:
                if event.key == pygame.K_1: player.weapon = "sniper"; choosing_weapon = False
                if event.key == pygame.K_2: player.weapon = "shotgun"; choosing_weapon = False
                if event.key == pygame.K_3: player.weapon = "ak"; choosing_weapon = False

    keys = pygame.key.get_pressed()

    if not game_over and not choosing_weapon:
        player_group.update(dt, keys)
        if (keys[pygame.K_SPACE] or keys[pygame.K_z]) and player.can_shoot(now):
            player.shoot(bullets, now)
        bullets.update(dt)
        enemies.update(dt)
        enemy_bullets.update(dt)

        # логика ShooterEnemy: они стреляют в игрока
        for e in [en for en in enemies if getattr(en, "type", "") == "shooter"]:
            if isinstance(e, ShooterEnemy):
                e.timer += dt
                if e.timer >= e.shoot_interval:
                    e.timer = 0
                    # стреляем в сторону игрока
                    dx = player.rect.centerx - e.rect.centerx
                    dy = player.rect.centery - e.rect.centery
                    dist = math.hypot(dx, dy) + 1e-6
                    vx = (dx / dist) * (BULLET_SPEED * 0.6)
                    vy = (dy / dist) * (BULLET_SPEED * 0.6)
                    enemy_bullets.add(Bullet(e.rect.centerx, e.rect.bottom + 6, vx=vx, vy=vy, damage=1.0, color=(200,120,120), friendly=False))

        # попадания: враг <— дружеские пули
        hits = pygame.sprite.groupcollide(enemies, bullets, False, True)
        for enemy_obj, bullet_list in hits.items():
            for b in bullet_list:
                enemy_obj.health -= b.damage
                create_particles(b.rect.centerx, b.rect.centery, (255,200,50), amount=6)
            if enemy_obj.health <= 0:
                # уничтожение с эффектом
                create_particles(enemy_obj.rect.centerx, enemy_obj.rect.centery, (255, 120, 40), amount=25)
                try:
                    if explosion_sound: explosion_sound.play()
                except:
                    pass
                # бонус за разные типы
                if getattr(enemy_obj, "type", "") == "shielded":
                    score += 30
                elif getattr(enemy_obj, "type", "") == "kamikaze":
                    score += 20
                elif getattr(enemy_obj, "type", "") == "shooter":
                    score += 18
                else:
                    score += 10
                enemy_obj.kill()

        # попадания игрока об врагов
        enemy_hits = pygame.sprite.spritecollide(player, enemies, True)
        if enemy_hits:
            player.health -= len(enemy_hits)
            create_particles(player.rect.centerx, player.rect.centery, (255,50,50), amount=18)
            if player.health <= 0:
                game_over = True

        # попадания игрока от вражеских пуль
        hits2 = pygame.sprite.spritecollide(player, enemy_bullets, True)
        if hits2:
            total_damage = sum(b.damage for b in hits2)
            player.health -= int(math.ceil(total_damage))
            create_particles(player.rect.centerx, player.rect.centery, (255,50,50), amount=10)
            if player.health <= 0:
                game_over = True

        # LEVEL UP каждые 100 очков
        if score // 100 + 1 > level:
            level += 1
            enemy_size_boost += 0.12
            enemy_speed_boost += 0.18
            if player.health < PLAYER_MAX_HEALTH:
                player.health += 1
            if levelup_sound: levelup_sound.play()
            level_up_time = now
            if level % 5 == 0:
                choosing_weapon = True

    # --- Рендер ---
    screen.fill((18, 18, 28))
    enemies.draw(screen)
    bullets.draw(screen)
    enemy_bullets.draw(screen)
    player_group.draw(screen)
    update_particles(screen)
    draw_hud()

    elapsed = now - level_up_time
    if 0 < elapsed < LEVEL_UP_DURATION:
        progress = elapsed / LEVEL_UP_DURATION
        alpha = int(255 * (progress*2 if progress < 0.5 else (2 - progress*2)))
        text = big_font.render("LEVEL UP!", True, (255, 255, 100))
        text.set_alpha(alpha)
        screen.blit(text, text.get_rect(center=(WIDTH // 2, HEIGHT // 2)))

    if choosing_weapon: show_weapon_choice()
    if game_over: show_game_over()

    pygame.display.flip()

pygame.quit()
