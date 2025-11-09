let currentChat = null;

// === Загрузка списка чатов ===
async function loadChats() {
  try {
    const response = await fetch('/get_chats');
    const chats = await response.json();
    const list = document.getElementById('chatList');
    list.innerHTML = '';

    chats.forEach(chat => {
      const div = document.createElement('div');
      div.className = `chat-item${chat.name === currentChat ? ' active' : ''}`;
      div.textContent = chat.title;
      div.onclick = () => switchChat(chat.name);
      list.appendChild(div);
    });
  } catch (err) {
    console.error('Ошибка при загрузке чатов:', err);
  }
}

// === Переключение между чатами ===
async function switchChat(name) {
  try {
    currentChat = name;
    const response = await fetch('/load_chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chat: name })
    });
    const data = await response.json();
    renderMessages(data.history || []);
    await loadChats();
  } catch (err) {
    console.error('Ошибка при переключении чата:', err);
  }
}

// === Создание нового чата ===
async function newChat() {
  try {
    const response = await fetch('/new_chat', { method: 'POST' });
    const data = await response.json();
    currentChat = data.new_chat;
    document.getElementById('chatBox').innerHTML = '';
    await loadChats();
  } catch (err) {
    console.error('Ошибка при создании чата:', err);
  }
}

// === Отображение сообщений ===
function renderMessages(messages) {
  const box = document.getElementById('chatBox');
  box.innerHTML = '';

  messages.forEach(msg => {
    const div = document.createElement('div');
    div.className = `msg ${msg.sender === 'user' ? 'user' : 'bot'}`;
    div.innerHTML = `<strong>${msg.sender === 'user' ? 'Ты' : 'Бот'}:</strong> ${msg.text.replace(/\n/g, '<br>')}`;

    if (msg.image_url) {
      const img = document.createElement('img');
      img.src = msg.image_url;
      img.alt = 'Изображение';
      div.appendChild(img);
    }

    box.appendChild(div);
  });

  box.scrollTop = box.scrollHeight;
}

// === Предпросмотр изображения перед отправкой ===
document.getElementById('imageInput').addEventListener('change', e => {
  const file = e.target.files[0];
  if (!file) return;

  const reader = new FileReader();
  reader.onload = ev => {
    const img = document.createElement('img');
    img.src = ev.target.result;
    const preview = document.createElement('div');
    preview.className = 'msg user';
    preview.appendChild(img);
    document.getElementById('chatBox').appendChild(preview);
  };
  reader.readAsDataURL(file);
});

// === Отправка сообщения ===
async function sendMsg() {
  const input = document.getElementById('msgInput');
  const fileInput = document.getElementById('imageInput');
  const text = input.value.trim();

  if (!text && !fileInput.files[0]) return;

  const box = document.getElementById('chatBox');
  const userDiv = document.createElement('div');
  userDiv.className = 'msg user';
  userDiv.innerHTML = `<strong>Ты:</strong> ${text.replace(/\n/g, '<br>')}`;
  box.appendChild(userDiv);
  box.scrollTop = box.scrollHeight;
  input.value = '';

  let image_url = null;

  // === Загрузка изображения, если есть ===
  if (fileInput.files[0]) {
    const formData = new FormData();
    formData.append('image', fileInput.files[0]);

    try {
      const response = await fetch('/upload_image', { method: 'POST', body: formData });
      const data = await response.json();
      if (data.image_url) {
        image_url = data.image_url;
        const img = document.createElement('img');
        img.src = data.image_url;
        userDiv.appendChild(img);
      }
    } catch (err) {
      console.error('Ошибка при загрузке изображения:', err);
    }

    fileInput.value = '';
  }

  // === Отправка сообщения боту ===
  try {
    const response = await fetch('/get', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ msg: text, image_url, chat: currentChat })
    });
    const data = await response.json();

    const botDiv = document.createElement('div');
    botDiv.className = 'msg bot';
    botDiv.innerHTML = `<strong>Бот:</strong> ${(data.response || '(нет ответа)').replace(/\n/g, '<br>')}`;
    box.appendChild(botDiv);
    box.scrollTop = box.scrollHeight;

    if (data.chat_name) {
      currentChat = data.chat_name;
      await loadChats();
    }
  } catch (err) {
    console.error('Ошибка при отправке сообщения:', err);
  }
}

// === Отправка по Enter ===
document.getElementById('msgInput').addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMsg();
  }
});

// === При загрузке страницы ===
window.onload = async () => {
  await loadChats();
  try {
    const chats = await (await fetch('/get_chats')).json();
    if (chats.length > 0) {
      currentChat = chats[0].name;
      await switchChat(currentChat);
    }
  } catch (err) {
    console.error('Ошибка при инициализации:', err);
  }
};
