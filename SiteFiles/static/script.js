const boards = {
    b: {
        title: "/b/ - Бред",
        description: "Истории и информация, размещённые здесь, являются художественным произведением, состоящим из вымысла и лжи. Только дурак будет принимать всё, что размещено здесь, за факты."
    },
    vg: {
        title: "/vg/ - Видеоигры",
        description: "Обсуждение видеоигр, новостей и всего, что связано с играми."
    },
    po: {
        title: "/po/ - Политика",
        description: "Обсуждение политических событий и актуальных тем."
    },
    mu: {
        title: "/mu/ - Музыка",
        description: "Все о музыке: жанры, исполнители, новинки."
    },
    news: {
        title: "/news/ - Новости",
        description: "Новости и актуальные события со всего мира."
    },
    ai: {
        title: "/ai/ - Искусственный интеллект",
        description: "Обсуждение искусственного интеллекта и его применения."
    },
    mov: {
        title: "/mov/ - Фильмы",
        description: "Обсуждение фильмов, сериалов и новинок кино."
    },
    dev: {
        title: "/dev/ - Разработка",
        description: "Разработка программного обеспечения, советы и обмен опытом."
    },
    sp: {
        title: "/sp/ - Спорт",
        description: "Обсуждение спортивных событий и новостей."
    },
    zog: {
        title: "/zog/ - Теории заговора",
        description: "Обсуждение различных теорий заговора."
    },
    biz: {
        title: "/biz/ - Бизнес",
        description: "Новости и обсуждения из мира бизнеса."
    },
    sn: {
        title: "/sn/ - Паранормальное",
        description: "Обсуждение паранормальных явлений и загадок."
    },
    a: {
        title: "/a/ - Аниме",
        description: "Все об аниме: новости, обсуждения, рекомендации."
    },
    v: {
        title: "/v/ - Видео",
        description: "Обсуждение видео и видеоконтента."
    }
};

document.addEventListener("DOMContentLoaded", async () => {
    const boardKey = getBoardKeyFromURL();
    const user = getUserFromLocalStorage();

    if (!user) return alertAndRedirect('You need to be logged in to access this page.');

    const board = boards[boardKey];
    if (board) {
        displayBoardDetails(board);
        await loadThreads(boardKey);
        setupSocket(boardKey);
    } else {
        console.error('Board not found:', boardKey);
    }

    setupUIEventListeners();

    function getBoardKeyFromURL() {
        return new URLSearchParams(window.location.search).get('board');
    }

    function getUserFromLocalStorage() {
        const user_id = localStorage.getItem('user_id'), user_code = localStorage.getItem('user_code');
        return user_id && user_code ? { user_id, user_code } : null;
    }

    function alertAndRedirect(message) {
        console.error(message);
        alert(message);
        window.history.back();
    }

    function displayBoardDetails(board) {
        document.getElementById('board-title').textContent = board.title;
        document.getElementById('board-description').textContent = board.description;
    }

    async function loadThreads(boardKey) {
        try {
            const threads = (await fetchJSON(`/api/threads/${boardKey}`)).sort((a, b) => new Date(b.date) - new Date(a.date));
            const threadsContainer = document.getElementById('threads-container');
            threadsContainer.innerHTML = '';

            for (const thread of threads) {
                const user = thread.user_id ? await fetchJSON(`/api/user/${thread.user_id}`) : null;
                const lastMessage = thread.message_count > 0 ? await fetchJSON(`/api/threads/${thread.id}/last_message`).catch(() => null) : null;
                addThread(thread, user, lastMessage);
            }
        } catch (error) {
            console.error('Error loading threads:', error);
        }
    }

    function addThread(thread, user, lastMessage) {
        const threadsContainer = document.getElementById('threads-container');
        const threadCard = createThreadCard(thread, user, lastMessage);
        threadsContainer.appendChild(threadCard);
    }

    function createThreadCard(thread, user, lastMessage) {
        const card = document.createElement('div'), img = document.createElement('img'), messages = document.createElement('div'), anonInfo = document.createElement('div');
        card.className = 'thread-card';
        img.className = 'thread-image';
        img.src = thread.image;
        img.alt = 'Изображение треда';
        messages.className = 'thread-messages';
        anonInfo.innerHTML = `<strong>Анонимус ${thread.date} №${user ? user.user_code : 'неизвестно'}</strong><br><p>${thread.title}</p>`;
        messages.appendChild(anonInfo);

        if (lastMessage) {
            const lastMsgDiv = document.createElement('div');
            lastMsgDiv.className = 'last-message';
            lastMsgDiv.innerHTML = `<strong>Анонимус ${lastMessage.date} №${lastMessage.user_code}</strong><br><p>${lastMessage.message}</p>`;
            messages.appendChild(lastMsgDiv);
        }

        const threadLinkBtn = document.createElement('button');
        threadLinkBtn.className = 'thread-link-button';
        threadLinkBtn.textContent = 'Перейти в тред';
        threadLinkBtn.addEventListener('click', () => window.location.href = `thread.html?board=${boardKey}&threadId=${thread.id}`);
        messages.appendChild(threadLinkBtn);
        card.appendChild(img);
        card.appendChild(messages);
        return card;
    }

    async function fetchJSON(url) {
        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        return response.json();
    }

    function setupSocket(boardKey) {
        const socket = io();
        socket.emit('join_board', { board: boardKey });
        socket.on('new_thread', data => { if (data.board === boardKey) loadThreads(boardKey); });
    }

    function setupUIEventListeners() {
        const modal = document.getElementById('modal'), newThreadButton = document.getElementById('new-thread-button'), closeButton = document.querySelector('.close-button');
        const newThreadForm = document.getElementById('new-thread-form'), threadImageInput = document.getElementById('thread-image-input'), imagePreview = document.getElementById('image-preview');
        const backButton = document.getElementById('back-button');

        newThreadButton.addEventListener('click', () => modal.style.display = 'block');
        closeButton.addEventListener('click', () => modal.style.display = 'none');
        window.addEventListener('click', event => { if (event.target === modal) modal.style.display = 'none'; });
        threadImageInput.addEventListener('change', () => previewImage(threadImageInput, imagePreview));
        newThreadForm.addEventListener('submit', event => handleNewThreadSubmit(event, boardKey, user, threadImageInput, imagePreview, newThreadForm, modal));
        backButton.addEventListener('click', () => window.history.back());
    }

    function previewImage(input, previewElement) {
        const file = input.files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = e => { previewElement.src = e.target.result; previewElement.classList.remove('hidden'); };
            reader.readAsDataURL(file);
        } else {
            previewElement.classList.add('hidden');
        }
    }

    async function handleNewThreadSubmit(event, boardKey, user, imageInput, imagePreview, form, modal) {
        event.preventDefault();

        const threadTitle = document.getElementById('thread-title').value, threadImage = imageInput.files[0];
        if (!threadImage) return alert('Please select an image for the thread.');

        const reader = new FileReader();
        reader.onload = async e => {
            const imageSrc = e.target.result;
            const threadData = { board: boardKey, title: threadTitle, image: imageSrc, user_id: user.user_id };

            try {
                const response = await fetch('/api/threads', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(threadData) });
                if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

                const data = await response.json();
                addThread(data.id, data.image, { date: data.date, user_code: user.user_code }, threadTitle, null);
                await loadThreads(boardKey);
            } catch (error) {
                console.error('Error creating thread:', error);
                alert('Error creating thread. Please try again.');
            }

            resetNewThreadForm(imagePreview, form, modal);
        };
        reader.readAsDataURL(threadImage);
    }

    function resetNewThreadForm(imagePreview, form, modal) {
        imagePreview.src = '#';
        imagePreview.classList.add('hidden');
        form.reset();
        modal.style.display = 'none';
    }
});
