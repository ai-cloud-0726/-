const BOARD_SIZE = 15;
const PLAYERS = ["black", "white"];
const OPPONENT = { black: "white", white: "black" };

const SKILL_POOL = ["flip", "avalanche", "swap", "shield", "tableFlip"];

const SKILLS = {
  flip: {
    id: "flip",
    name: "颠倒黑白",
    description: "点击对方的一个棋子并替换为己方棋子。",
    icon: "♻️",
    color: "linear-gradient(135deg, #5c6bf2, #1f2bd9)",
    needsTarget: "opponentPiece",
    interceptable: true,
  },
  avalanche: {
    id: "avalanche",
    name: "排山倒海",
    description: "随机选择对方三子向对方向推移一格。",
    icon: "🌊",
    color: "linear-gradient(135deg, #69d8ff, #1189c8)",
    needsTarget: null,
    interceptable: true,
  },
  swap: {
    id: "swap",
    name: "偷梁换柱",
    description: "随机将对方的一个棋子变为己方棋子。",
    icon: "🎭",
    color: "linear-gradient(135deg, #ff8ad0, #d11aff)",
    needsTarget: null,
    interceptable: true,
  },
  shield: {
    id: "shield",
    name: "无懈可击",
    description: "被动：抵挡对方一次技能。",
    icon: "🛡",
    color: "linear-gradient(135deg, #a4ffd6, #17d1aa)",
    needsTarget: null,
    interceptable: false,
    passive: true,
  },
  tableFlip: {
    id: "tableFlip",
    name: "掀桌",
    description: "立刻判定平局。",
    icon: "💥",
    color: "linear-gradient(135deg, #ffb46b, #ff5252)",
    needsTarget: null,
    interceptable: true,
  },
};

const NAME_PARTS = {
  prefix: ["神秘", "迅捷", "妙手", "无双", "沉着", "灵动", "暴风", "星辉", "竹影", "玄武"],
  suffix: ["棋圣", "棋魂", "落子", "指挥官", "策士", "漫游者", "守望者", "使者", "幻术师", "旅人"],
};

const boardEl = document.getElementById("board");
const turnBanner = document.getElementById("turnBanner");
const startButton = document.getElementById("startButton");
const boardOverlay = document.getElementById("boardOverlay");
const animationsLayer = document.getElementById("animationsLayer");
const scoreBlackEl = document.getElementById("scoreBlack");
const scoreWhiteEl = document.getElementById("scoreWhite");
const scoreDrawEl = document.getElementById("scoreDraw");
const tooltip = createTooltip();

document.body.appendChild(tooltip);

const state = {
  board: createBoard(),
  started: false,
  currentPlayer: "black",
  winner: null,
  moves: 0,
  skills: {
    black: [null, null, null],
    white: [null, null, null],
  },
  skillProgress: {
    black: { turns: 0 },
    white: { turns: 0 },
  },
  totals: {
    black: 0,
    white: 0,
    draw: 0,
  },
  roundScore: {
    black: 0,
    white: 0,
  },
  pendingSkill: null,
  waitingShield: null,
};

const playerPanels = {
  black: document.querySelector('[data-player="black"]'),
  white: document.querySelector('[data-player="white"]'),
};

const shieldPrompts = {
  black: document.querySelector('[data-shield-prompt="black"]'),
  white: document.querySelector('[data-shield-prompt="white"]'),
};

const skillBars = {
  black: document.querySelector('[data-player-skillbar="black"]'),
  white: document.querySelector('[data-player-skillbar="white"]'),
};

const avatarEls = {
  black: document.querySelector('[data-player-avatar="black"]'),
  white: document.querySelector('[data-player-avatar="white"]'),
};

const nameEls = {
  black: document.querySelector('[data-player-name="black"]'),
  white: document.querySelector('[data-player-name="white"]'),
};

const roundScoreEls = {
  black: document.querySelector('[data-round-score="black"]'),
  white: document.querySelector('[data-round-score="white"]'),
};

init();

function init() {
  renderBoard();
  initPlayers();
  attachEventListeners();
  updateCursor();
  updateSkillSlots();
  updateForbiddenMarkers();
}

function initPlayers() {
  PLAYERS.forEach((player) => {
    const name = `${randomItem(NAME_PARTS.prefix)}${randomItem(NAME_PARTS.suffix)}`;
    nameEls[player].textContent = name;
    avatarEls[player].src = generateAvatar(name);
  });
}

function renderBoard() {
  boardEl.innerHTML = "";
  for (let row = 0; row < BOARD_SIZE; row += 1) {
    for (let col = 0; col < BOARD_SIZE; col += 1) {
      const cell = document.createElement("div");
      cell.className = "cell";
      cell.dataset.row = row;
      cell.dataset.col = col;
      cell.setAttribute("role", "gridcell");
      cell.setAttribute("aria-label", `(${row + 1},${col + 1})`);
      const marker = document.createElement("div");
      marker.className = "forbidden-marker";
      marker.textContent = "×";
      cell.appendChild(marker);
      boardEl.appendChild(cell);
    }
  }
}

function attachEventListeners() {
  startButton.addEventListener("click", startGame);
  boardEl.addEventListener("click", handleBoardClick);
  boardEl.addEventListener("mousemove", handleBoardHover);
  boardEl.addEventListener("mouseleave", () => hideTooltip());

  document.querySelectorAll(".skill-slot").forEach((slot) => {
    slot.addEventListener("click", () => onSkillSlotClick(slot));
    const discard = slot.querySelector("[data-action='discard']");
    discard.addEventListener("click", (event) => {
      event.stopPropagation();
      const player = slot.dataset.player;
      const index = Number(slot.dataset.slotIndex);
      discardSkill(player, index);
    });
  });

  document.querySelectorAll("[data-action='change-avatar']").forEach((button) => {
    button.addEventListener("click", () => {
      const player = button.dataset.player;
      avatarEls[player].src = generateAvatar(nameEls[player].textContent.trim() || player);
    });
  });

  Object.entries(shieldPrompts).forEach(([player, prompt]) => {
    prompt.querySelector("[data-action='shield-confirm']").addEventListener("click", () => {
      if (!state.waitingShield || state.waitingShield.player !== player) return;
      hideShieldPrompt(player);
      consumeShield(player);
      playShieldAnimation(player);
      const { onResolve } = state.waitingShield;
      state.waitingShield = null;
      if (onResolve) onResolve(true);
    });
    prompt.querySelector("[data-action='shield-decline']").addEventListener("click", () => {
      if (!state.waitingShield || state.waitingShield.player !== player) return;
      hideShieldPrompt(player);
      const { onResolve } = state.waitingShield;
      state.waitingShield = null;
      if (onResolve) onResolve(false);
    });
  });
}

function startGame() {
  resetState();
  state.started = true;
  startButton.style.display = "none";
  boardOverlay.innerHTML = "";
  setTimeout(() => showTurnBanner(state.currentPlayer), 60);
  updateCursor();
  updateForbiddenMarkers();
  PLAYERS.forEach((player) => {
    maybeAwardSkill(player, true);
  });
}

function resetState() {
  state.board = createBoard();
  state.currentPlayer = "black";
  state.winner = null;
  state.moves = 0;
  state.pendingSkill = null;
  state.waitingShield = null;
  state.roundScore.black = 0;
  state.roundScore.white = 0;
  state.skills = {
    black: [null, null, null],
    white: [null, null, null],
  };
  state.skillProgress = {
    black: { turns: 0 },
    white: { turns: 0 },
  };
  roundScoreEls.black.textContent = "0";
  roundScoreEls.white.textContent = "0";
  Array.from(boardEl.querySelectorAll(".piece")).forEach((piece) => piece.remove());
  clearTargetHighlights();
  PLAYERS.forEach((player) => hideShieldPrompt(player));
  hideTooltip();
  document.querySelectorAll(".skill-slot").forEach((slot) => {
    slot.dataset.hasSkill = "false";
    slot.dataset.skillId = "";
    slot.dataset.disabled = "false";
    slot.removeAttribute("data-highlight");
    const icon = slot.querySelector("[data-skill-icon]");
    icon.style.background = "transparent";
    icon.textContent = "";
    icon.removeAttribute("title");
  });
}

function handleBoardClick(event) {
  const target = event.target.closest(".cell");
  if (!target) return;
  const row = Number(target.dataset.row);
  const col = Number(target.dataset.col);

  if (state.pendingSkill) {
    handleSkillTargetSelection(target, row, col);
    return;
  }

  if (!state.started || state.winner) return;

  if (state.board[row][col]) return;

  if (state.currentPlayer === "black" && target.dataset.forbidden === "true") {
    showTooltip(target, target.dataset.forbiddenTip || "该点为黑方禁手");
    return;
  }

  placeStone(row, col, state.currentPlayer);
  const color = state.currentPlayer;
  if (checkWin(row, col, color)) {
    finishGame(color);
    return;
  }
  if (state.moves === BOARD_SIZE * BOARD_SIZE) {
    finishGame(null);
    return;
  }

  maybeAwardSkill(color);
  switchTurn();
}

function handleBoardHover(event) {
  const cell = event.target.closest(".cell");
  if (!cell) {
    hideTooltip();
    return;
  }
  if (cell.dataset.forbidden === "true" && state.currentPlayer === "black") {
    showTooltip(cell, cell.dataset.forbiddenTip || "黑方禁手");
  } else {
    hideTooltip();
  }
}

function placeStone(row, col, color) {
  state.board[row][col] = color;
  state.moves += 1;
  const cell = getCell(row, col);
  const piece = document.createElement("div");
  piece.className = `piece ${color}`;
  cell.appendChild(piece);
  updateForbiddenMarkers();
}

function switchTurn() {
  state.currentPlayer = OPPONENT[state.currentPlayer];
  updateCursor();
  setTimeout(() => showTurnBanner(state.currentPlayer), 0);
}

function finishGame(winner) {
  state.started = false;
  state.winner = winner;
  startButton.style.display = "block";
  startButton.textContent = "再来一局";

  if (winner) {
    state.roundScore[winner] += 1;
    state.totals[winner] += 1;
    showVictoryAnimation(winner);
  } else {
    state.totals.draw += 1;
    showDrawAnimation();
  }
  roundScoreEls.black.textContent = state.roundScore.black.toString();
  roundScoreEls.white.textContent = state.roundScore.white.toString();
  scoreBlackEl.textContent = state.totals.black.toString();
  scoreWhiteEl.textContent = state.totals.white.toString();
  scoreDrawEl.textContent = state.totals.draw.toString();
}

function showVictoryAnimation(winner) {
  boardOverlay.innerHTML = "";
  const overlay = document.createElement("div");
  overlay.className = "victory-overlay";
  const text = document.createElement("span");
  text.textContent = "神之一手";
  overlay.appendChild(text);
  boardOverlay.appendChild(overlay);
}

function showDrawAnimation() {
  boardOverlay.innerHTML = "";
  const overlay = document.createElement("div");
  overlay.className = "draw-overlay";
  const text = document.createElement("span");
  text.textContent = "本局平局";
  overlay.appendChild(text);
  boardOverlay.appendChild(overlay);
}

function showTurnBanner(player) {
  if (!state.started) return;
  turnBanner.textContent = player === "black" ? "黑棋落子" : "白棋落子";
  turnBanner.classList.remove("show");
  void turnBanner.offsetWidth;
  turnBanner.classList.add("show");
}

function updateCursor() {
  const color = state.currentPlayer;
  document.body.style.cursor = `url(${generateCursor(color)}), auto`;
}

function generateCursor(color) {
  const size = 32;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, size, size);
  ctx.beginPath();
  ctx.arc(size / 2, size / 2, size / 2 - 1, 0, Math.PI * 2);
  const gradient = ctx.createRadialGradient(size * 0.3, size * 0.3, size * 0.2, size / 2, size / 2, size / 2);
  if (color === "black") {
    gradient.addColorStop(0, "#555");
    gradient.addColorStop(1, "#111");
  } else {
    gradient.addColorStop(0, "#fff");
    gradient.addColorStop(1, "#b0b0b0");
  }
  ctx.fillStyle = gradient;
  ctx.fill();
  ctx.lineWidth = 2;
  ctx.strokeStyle = "rgba(0,0,0,0.45)";
  ctx.stroke();
  return canvas.toDataURL();
}

function updateSkillSlots() {
  PLAYERS.forEach((player) => {
    state.skills[player].forEach((skill, index) => {
      const slot = getSkillSlot(player, index);
      renderSkillSlot(slot, skill);
    });
  });
}

function renderSkillSlot(slot, skill) {
  const icon = slot.querySelector("[data-skill-icon]");
  if (skill) {
    const definition = SKILLS[skill.id];
    if (!definition) {
      console.warn("Unknown skill id", skill.id);
      slot.dataset.hasSkill = "false";
      slot.dataset.skillId = "";
      icon.textContent = "";
      icon.style.background = "transparent";
      icon.removeAttribute("title");
      slot.dataset.disabled = "false";
      return;
    }
    slot.dataset.hasSkill = "true";
    slot.dataset.skillId = skill.id;
    icon.textContent = definition.icon;
    icon.style.background = definition.color;
    icon.title = `${definition.name}\n${definition.description}`;
    slot.dataset.disabled = definition.passive ? "true" : "false";
  } else {
    slot.dataset.hasSkill = "false";
    slot.dataset.skillId = "";
    icon.textContent = "";
    icon.style.background = "transparent";
    icon.removeAttribute("title");
    slot.dataset.disabled = "false";
  }
}

function onSkillSlotClick(slot) {
  const player = slot.dataset.player;
  const index = Number(slot.dataset.slotIndex);
  const skill = state.skills[player][index];
  if (!skill || state.winner || !state.started) return;
  if (skill.id === "shield") return;
  if (player !== state.currentPlayer) return;
  if (state.pendingSkill) return;

  const skillInfo = SKILLS[skill.id];

  if (!canUseSkillNow(player, skillInfo)) {
    showTooltip(slot, "当前没有可选目标");
    setTimeout(() => hideTooltip(), 1500);
    return;
  }

  const execute = () => {
    consumeSkill(player, index);
    if (skillInfo.needsTarget === "opponentPiece") {
      state.pendingSkill = { player, skill: skillInfo, slotIndex: index };
      highlightTargetablePieces(OPPONENT[player]);
    } else {
      triggerSkillEffect(player, skillInfo);
    }
  };

  if (skillInfo.interceptable) {
    tryIntercept(player, skillInfo, execute);
  } else {
    execute();
  }
}

function canUseSkillNow(player, skill) {
  if (skill.needsTarget !== "opponentPiece") return true;
  const opponent = OPPONENT[player];
  return collectPieces(opponent).length > 0;
}

function handleSkillTargetSelection(cell, row, col) {
  const { pendingSkill } = state;
  if (!pendingSkill) return;
  if (pendingSkill.skill.needsTarget === "opponentPiece") {
    const opponent = OPPONENT[pendingSkill.player];
    if (state.board[row][col] !== opponent) return;
    clearTargetHighlights();
    consumeSkill(pendingSkill.player, pendingSkill.slotIndex, false);
    state.board[row][col] = pendingSkill.player;
    const piece = getCell(row, col).querySelector(".piece");
    if (piece) {
      piece.classList.remove(opponent);
      piece.classList.add(pendingSkill.player);
    }
    showSkillActivation(pendingSkill.player, pendingSkill.skill);
    state.pendingSkill = null;
    if (checkWin(row, col, pendingSkill.player)) {
      finishGame(pendingSkill.player);
      return;
    }
    updateForbiddenMarkers();
  }
}

function triggerSkillEffect(player, skill) {
  switch (skill.id) {
    case "avalanche":
      performAvalanche(player);
      break;
    case "swap":
      performSwap(player);
      break;
    case "tableFlip":
      showSkillActivation(player, skill);
      finishGame(null);
      break;
    default:
      break;
  }
}

function performSwap(player) {
  const opponent = OPPONENT[player];
  const opponentPieces = collectPieces(opponent);
  if (opponentPieces.length === 0) return;
  const target = randomItem(opponentPieces);
  const { row, col } = target;
  state.board[row][col] = player;
  const piece = getCell(row, col).querySelector(".piece");
  if (piece) {
    piece.classList.remove(opponent);
    piece.classList.add(player);
  }
  showSkillActivation(player, SKILLS.swap);
  if (checkWin(row, col, player)) {
    finishGame(player);
  }
  updateForbiddenMarkers();
}

function performAvalanche(player) {
  const opponent = OPPONENT[player];
  const opponentPieces = shuffle(collectPieces(opponent));
  const affected = opponentPieces.slice(0, Math.min(3, opponentPieces.length));
  if (affected.length === 0) {
    showSkillActivation(player, SKILLS.avalanche);
    return;
  }
  const direction = player === "black" ? 1 : -1;
  affected.forEach(({ row, col }) => {
    let currentCol = col;
    let nextCol = currentCol + direction;
    while (nextCol >= 0 && nextCol < BOARD_SIZE) {
      if (!state.board[row][nextCol]) {
        break;
      }
      currentCol = nextCol;
      nextCol += direction;
    }
    const originCell = getCell(row, col);
    const piece = originCell.querySelector(".piece");
    state.board[row][col] = null;
    if (nextCol < 0 || nextCol >= BOARD_SIZE) {
      if (piece) piece.remove();
    } else {
      state.board[row][nextCol] = opponent;
      const targetCell = getCell(row, nextCol);
      if (piece) {
        piece.remove();
        targetCell.appendChild(piece);
      }
    }
  });
  showSkillActivation(player, SKILLS.avalanche);
  updateForbiddenMarkers();
  recountPieces();
}

function consumeSkill(player, index, remove = true) {
  const skill = state.skills[player][index];
  if (!skill) return;
  if (remove) state.skills[player][index] = null;
  const slot = getSkillSlot(player, index);
  slot.removeAttribute("data-highlight");
  renderSkillSlot(slot, remove ? null : skill);
}

function discardSkill(player, index) {
  if (!state.skills[player][index]) return;
  state.skills[player][index] = null;
  const slot = getSkillSlot(player, index);
  slot.removeAttribute("data-highlight");
  renderSkillSlot(slot, null);
}

function tryIntercept(player, skill, proceed) {
  const opponent = OPPONENT[player];
  const shieldIndex = state.skills[opponent].findIndex((s) => s && s.id === "shield");
  if (shieldIndex === -1) {
    proceed();
    return;
  }
  if (state.waitingShield) return;
  state.waitingShield = {
    player: opponent,
    shieldIndex,
    onResolve: (used) => {
      if (!used) {
        proceed();
      }
    },
  };
  showShieldPrompt(opponent);
}

function consumeShield(player) {
  const shieldIndex = state.skills[player].findIndex((s) => s && s.id === "shield");
  if (shieldIndex === -1) return;
  state.skills[player][shieldIndex] = null;
  const slot = getSkillSlot(player, shieldIndex);
  renderSkillSlot(slot, null);
}

function showShieldPrompt(player) {
  const prompt = shieldPrompts[player];
  prompt.dataset.visible = "true";
  prompt.setAttribute("aria-hidden", "false");
}

function hideShieldPrompt(player) {
  const prompt = shieldPrompts[player];
  prompt.dataset.visible = "false";
  prompt.setAttribute("aria-hidden", "true");
}

function maybeAwardSkill(player, force = false) {
  const progress = state.skillProgress[player];
  const emptySlotIndex = state.skills[player].findIndex((skill) => !skill);
  if (emptySlotIndex === -1) {
    progress.turns = 0;
    return;
  }
  progress.turns += 1;
  let grant = force;
  if (!grant) {
    const probability = Math.min(1, 0.2 * progress.turns);
    if (progress.turns >= 3) {
      grant = true;
    } else if (Math.random() < probability) {
      grant = true;
    }
  }
  if (grant) {
    progress.turns = 0;
    const skillId = randomItem(SKILL_POOL);
    const skill = { id: skillId };
    state.skills[player][emptySlotIndex] = skill;
    renderSkillSlot(getSkillSlot(player, emptySlotIndex), skill);
    playSkillGainAnimation(player, emptySlotIndex, SKILLS[skillId]);
  }
}

function playSkillGainAnimation(player, slotIndex, skill) {
  const panel = playerPanels[player];
  const slot = getSkillSlot(player, slotIndex);
  slot.dataset.highlight = "true";
  const gift = document.createElement("div");
  gift.className = "gift-drop";
  gift.textContent = "🎁";
  const panelRect = panel.getBoundingClientRect();
  gift.style.left = `${panelRect.left + panelRect.width / 2}px`;
  animationsLayer.appendChild(gift);
  setTimeout(() => {
    gift.remove();
    const fly = document.createElement("div");
    fly.className = "skill-fly";
    fly.textContent = skill.icon;
    fly.style.background = skill.color;
    const layerRect = animationsLayer.getBoundingClientRect();
    const slotRect = slot.getBoundingClientRect();
    const startX = panelRect.left + panelRect.width / 2 - layerRect.left - 28;
    const startY = panelRect.top + panelRect.height / 2 - layerRect.top - 28;
    fly.style.left = `${startX}px`;
    fly.style.top = `${startY}px`;
    const tx = slotRect.left + slotRect.width / 2 - (panelRect.left + panelRect.width / 2);
    const ty = slotRect.top + slotRect.height / 2 - (panelRect.top + panelRect.height / 2);
    fly.style.setProperty("--tx", `${tx}px`);
    fly.style.setProperty("--ty", `${ty}px`);
    animationsLayer.appendChild(fly);
    setTimeout(() => fly.remove(), 800);
  }, 860);
}

function playShieldAnimation(player) {
  const overlay = document.createElement("div");
  overlay.className = "shield-animation";
  boardOverlay.appendChild(overlay);
  setTimeout(() => overlay.remove(), 1400);
}

function showSkillActivation(player, skill) {
  const overlay = document.createElement("div");
  overlay.className = "skill-activation";
  const icon = document.createElement("div");
  icon.className = "skill-icon";
  icon.style.background = skill.color;
  icon.textContent = skill.icon;
  overlay.appendChild(icon);
  boardOverlay.appendChild(overlay);
  setTimeout(() => overlay.remove(), 800);
}

function collectPieces(color) {
  const pieces = [];
  for (let row = 0; row < BOARD_SIZE; row += 1) {
    for (let col = 0; col < BOARD_SIZE; col += 1) {
      if (state.board[row][col] === color) {
        pieces.push({ row, col });
      }
    }
  }
  return pieces;
}

function recountPieces() {
  let total = 0;
  for (let row = 0; row < BOARD_SIZE; row += 1) {
    for (let col = 0; col < BOARD_SIZE; col += 1) {
      if (state.board[row][col]) {
        total += 1;
      }
    }
  }
  state.moves = total;
}

function highlightTargetablePieces(opponent) {
  document.querySelectorAll(`.piece.${opponent}`).forEach((piece) => {
    piece.dataset.targetable = "true";
  });
}

function clearTargetHighlights() {
  document.querySelectorAll(".piece[data-targetable]").forEach((piece) => {
    delete piece.dataset.targetable;
  });
}

function createBoard() {
  return Array.from({ length: BOARD_SIZE }, () => Array(BOARD_SIZE).fill(null));
}

function getCell(row, col) {
  return boardEl.querySelector(`.cell[data-row='${row}'][data-col='${col}']`);
}

function getSkillSlot(player, index) {
  return skillBars[player].querySelector(`.skill-slot[data-slot-index='${index}']`);
}

function randomItem(array) {
  return array[Math.floor(Math.random() * array.length)];
}

function shuffle(array) {
  const copy = array.slice();
  for (let i = copy.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy;
}

function randomColorFromText(text) {
  let hash = 0;
  for (let i = 0; i < text.length; i += 1) {
    hash = text.charCodeAt(i) + ((hash << 5) - hash);
  }
  const hue = Math.abs(hash) % 360;
  return `hsl(${hue}, 65%, 60%)`;
}

function generateAvatar(seed) {
  const size = 128;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d");
  const color = randomColorFromText(seed);
  const gradient = ctx.createRadialGradient(size * 0.3, size * 0.3, 10, size * 0.6, size * 0.7, size * 0.8);
  gradient.addColorStop(0, lighten(color, 0.25));
  gradient.addColorStop(1, darken(color, 0.2));
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, size, size);
  ctx.fillStyle = "rgba(255,255,255,0.16)";
  ctx.beginPath();
  ctx.arc(size * 0.25, size * 0.35, size * 0.28, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "rgba(255,255,255,0.2)";
  ctx.beginPath();
  ctx.arc(size * 0.7, size * 0.65, size * 0.35, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "rgba(255, 255, 255, 0.9)";
  ctx.font = `${size * 0.4}px "Noto Sans SC", sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(seed[0] || "棋", size / 2, size / 2);
  return canvas.toDataURL();
}

function lighten(color, amount) {
  const { h, s, l } = parseHsl(color);
  return `hsl(${h}, ${s}%, ${Math.min(100, l + amount * 100)}%)`;
}

function darken(color, amount) {
  const { h, s, l } = parseHsl(color);
  return `hsl(${h}, ${s}%, ${Math.max(0, l - amount * 100)}%)`;
}

function parseHsl(color) {
  if (!color.startsWith("hsl")) {
    return { h: 30, s: 60, l: 55 };
  }
  const [h, s, l] = color
    .slice(color.indexOf("(") + 1, color.indexOf(")"))
    .split(",")
    .map((part) => parseFloat(part));
  return { h, s, l };
}

function showTooltip(element, text) {
  tooltip.textContent = text;
  const rect = element.getBoundingClientRect();
  tooltip.style.left = `${rect.left + rect.width / 2}px`;
  tooltip.style.top = `${rect.top - 12}px`;
  tooltip.classList.add("show");
}

function hideTooltip() {
  tooltip.classList.remove("show");
}

function createTooltip() {
  const tip = document.createElement("div");
  tip.className = "tooltip";
  return tip;
}

function checkWin(row, col, color) {
  const directions = [
    [1, 0],
    [0, 1],
    [1, 1],
    [1, -1],
  ];
  return directions.some(([dx, dy]) => countConsecutive(row, col, dx, dy, color) >= 5);
}

function countConsecutive(row, col, dx, dy, color) {
  let count = 1;
  let r = row + dx;
  let c = col + dy;
  while (isInside(r, c) && state.board[r][c] === color) {
    count += 1;
    r += dx;
    c += dy;
  }
  r = row - dx;
  c = col - dy;
  while (isInside(r, c) && state.board[r][c] === color) {
    count += 1;
    r -= dx;
    c -= dy;
  }
  return count;
}

function isInside(row, col) {
  return row >= 0 && col >= 0 && row < BOARD_SIZE && col < BOARD_SIZE;
}

function updateForbiddenMarkers() {
  const reasonsCache = new Map();
  for (let row = 0; row < BOARD_SIZE; row += 1) {
    for (let col = 0; col < BOARD_SIZE; col += 1) {
      const cell = getCell(row, col);
      if (state.board[row][col]) {
        cell.dataset.forbidden = "false";
        cell.dataset.forbiddenTip = "";
        continue;
      }
      const key = `${row},${col}`;
      const result = reasonsCache.get(key) || evaluateForbidden(row, col);
      reasonsCache.set(key, result);
      if (result.forbidden) {
        cell.dataset.forbidden = "true";
        cell.dataset.forbiddenTip = `黑方禁手：${result.reasons.join("、")}`;
      } else {
        cell.dataset.forbidden = "false";
        cell.dataset.forbiddenTip = "";
      }
    }
  }
}

function evaluateForbidden(row, col) {
  const reasons = [];
  state.board[row][col] = "black";
  if (createsOverline(row, col, "black")) {
    reasons.push("长连");
  }
  const openThrees = countOpenThrees(row, col, "black");
  if (openThrees >= 2) {
    reasons.push("双三");
  }
  const openFours = countOpenFours(row, col, "black");
  if (openFours >= 2) {
    reasons.push("双四");
  }
  state.board[row][col] = null;
  return { forbidden: reasons.length > 0, reasons };
}

function createsOverline(row, col, color) {
  const directions = [
    [1, 0],
    [0, 1],
    [1, 1],
    [1, -1],
  ];
  return directions.some(([dx, dy]) => countConsecutive(row, col, dx, dy, color) > 5);
}

function countOpenThrees(row, col, color) {
  let total = 0;
  const directions = [
    [1, 0],
    [0, 1],
    [1, 1],
    [1, -1],
  ];
  directions.forEach(([dx, dy]) => {
    const pattern = extractPattern(row, col, dx, dy, color);
    const matches = matchPatterns(pattern, [".XX.X.", ".X.XX.", "..XXX.", ".XXX..", ".XX..X", "X..XX."]);
    total += matches;
  });
  return total;
}

function countOpenFours(row, col, color) {
  let total = 0;
  const directions = [
    [1, 0],
    [0, 1],
    [1, 1],
    [1, -1],
  ];
  directions.forEach(([dx, dy]) => {
    const pattern = extractPattern(row, col, dx, dy, color);
    const matches = matchPatterns(pattern, [".XXXX.", "X.XXX.", ".XXX.X", ".XX.XX."]);
    total += matches;
  });
  return total;
}

function extractPattern(row, col, dx, dy, color) {
  const values = [];
  for (let step = -4; step <= 4; step += 1) {
    const r = row + step * dx;
    const c = col + step * dy;
    if (!isInside(r, c)) {
      values.push("W");
    } else if (state.board[r][c] === color) {
      values.push("X");
    } else if (state.board[r][c] === null) {
      values.push(".");
    } else {
      values.push("O");
    }
  }
  return values.join("");
}

function matchPatterns(pattern, patterns) {
  let count = 0;
  patterns.forEach((p) => {
    let start = 0;
    while (start <= pattern.length - p.length) {
      const segment = pattern.slice(start, start + p.length);
      if (comparePattern(segment, p)) {
        count += 1;
      }
      start += 1;
    }
  });
  return count;
}

function comparePattern(segment, template) {
  for (let i = 0; i < template.length; i += 1) {
    const t = template[i];
    if (segment[i] === "W") return false;
    if (t === "X" && segment[i] !== "X") return false;
    if (t === "." && segment[i] !== ".") return false;
    if (t === "O" && segment[i] === "X") return false;
  }
  return !segment.includes("O");
}
