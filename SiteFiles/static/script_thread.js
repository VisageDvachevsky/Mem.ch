document.addEventListener('DOMContentLoaded', async () => {
    const { board, threadId } = getUrlParams();
    const user = getUserFromLocalStorage();
    if (!user) return alertAndRedirect('You need to be logged in to access this page.');

    setupSocket(board, threadId);
    setupUIEventListeners();
    await Promise.all([fetchThreadInfo(board, threadId), fetchMessages(threadId)]);

    function getUrlParams() {
        const params = new URLSearchParams(window.location.search);
        return { board: params.get('board'), threadId: params.get('threadId') };
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

    async function fetchThreadInfo(board, threadId) {
        try {
            const data = await fetchJSON(`/api/threads/${board}`);
            const thread = data.find(t => t.id === parseInt(threadId));
            if (thread) {
                document.getElementById('board-name').textContent = `Доска: ${board}`;
                document.getElementById('thread-title').textContent = `Тред: ${thread.title}`;
            }
        } catch (error) { console.error('Error fetching thread info:', error); }
    }

    async function fetchMessages(threadId) {
        try {
            const data = await fetchJSON(`/api/threads/${threadId}/messages`);
            if (data.length > 50) await deleteOldMessages(threadId);
            const chatWindow = document.getElementById('chat-window');
            chatWindow.innerHTML = '';
            data.forEach(msg => chatWindow.appendChild(createMessageCard(msg)));
            chatWindow.scrollTop = chatWindow.scrollHeight;
        } catch (error) { console.error('Error fetching messages:', error); }
    }

    function createMessageCard(msg) {
        const card = document.createElement('div'), meta = document.createElement('div'), content = document.createElement('div');
        card.classList.add('message-card');
        meta.classList.add('message-meta');
        meta.textContent = `Анонимус ${msg.date} №${msg.user_code}`;
        content.classList.add('message-text');
        content.textContent = msg.message;
        if (msg.image) {
            const img = document.createElement('img');
            img.src = `data:image/*;base64,${msg.image}`;
            img.classList.add('message-image');
            img.onclick = () => openModal(msg.image);
            meta.appendChild(img);
        }
        card.appendChild(meta);
        meta.appendChild(content);
        return card;
    }

    async function deleteOldMessages(threadId) {
        try {
            const response = await fetch(`/api/threads/${threadId}/messages/delete_old`, { method: 'DELETE' });
            const data = await response.json();
            if (data.status === 'success') await fetchMessages(threadId);
            else console.error('Error deleting old messages:', data.error);
        } catch (error) { console.error('Error deleting old messages:', error); }
    }

    async function sendMessage(formData) {
        try {
            const response = await fetch('/api/messages', { method: 'POST', body: formData });
            const data = await response.json();
            if (data.error) console.error('Error sending message:', data.error);
            else {
                resetMessageForm();
                await fetchMessages(threadId);
            }
        } catch (error) { console.error('Error sending message:', error); }
    }

    function openModal(imageSrc) {
        const modal = document.getElementById("image-modal"), modalImage = document.getElementById("modal-image");
        modal.style.display = "block";
        modalImage.src = `data:image/*;base64,${imageSrc}`;
    }

    function closeModal() {
        document.getElementById("image-modal").style.display = "none";
    }

    function setupSocket(board, threadId) {
        const socket = io();
        socket.emit('join', { board, thread_id: threadId });
        socket.on('new_message', async data => { if (data.thread_id === parseInt(threadId)) await fetchMessages(threadId); });
        socket.on('new_thread', async data => { if (data.board === board) await fetchThreadInfo(board, threadId); });
    }

    function setupUIEventListeners() {
        const modal = document.getElementById("image-modal"), closeModalBtn = document.getElementById("close-modal");
        document.getElementById('send-message').addEventListener('click', handleSendMessage);
        document.getElementById('back-button').addEventListener('click', () => window.history.back());
        closeModalBtn.onclick = closeModal;
        window.onclick = event => { if (event.target === modal) closeModal(); };
    }

    async function handleSendMessage() {
        const messageText = document.getElementById('message-text').value.trim(), imageInput = document.getElementById('image-upload');
        if (!messageText && !imageInput.files.length) return console.log('Message not sent: messageText is empty and no image selected');
        const formData = new FormData();
        formData.append('thread_id', threadId);
        formData.append('user_id', user.user_id);
        formData.append('message', messageText);
        if (imageInput.files.length) formData.append('image', imageInput.files[0]);
        await sendMessage(formData);
    }

    function resetMessageForm() {
        document.getElementById('message-text').value = '';
        document.getElementById('image-upload').value = '';
    }

    async function fetchJSON(url) {
        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        return response.json();
    }
});
