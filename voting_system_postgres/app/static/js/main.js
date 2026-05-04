document.addEventListener('DOMContentLoaded', () => {
  const toggle = document.querySelector('.nav-toggle');
  const links = document.querySelector('.nav-links');
  if (toggle && links) {
    toggle.addEventListener('click', () => links.classList.toggle('open'));
  }

  const reveals = document.querySelectorAll('.reveal');
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12 });
    reveals.forEach(el => observer.observe(el));
  } else {
    reveals.forEach(el => el.classList.add('visible'));
  }

  document.querySelectorAll('.password-toggle').forEach((button) => {
    button.addEventListener('click', () => {
      const input = button.parentElement.querySelector('input');
      if (!input) return;
      const isPassword = input.type === 'password';
      input.type = isPassword ? 'text' : 'password';
      button.textContent = isPassword ? 'Hide' : 'Show';
    });
  });

  const widget = document.querySelector('.assistant-widget');
  const fab = document.querySelector('.assistant-fab');
  const close = document.querySelector('.assistant-close');
  const form = document.querySelector('.assistant-form');
  const messages = document.querySelector('.assistant-messages');
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';

  function addMessage(text, type) {
    if (!messages) return;
    const bubble = document.createElement('div');
    bubble.className = type === 'user' ? 'user-msg' : 'bot-msg';
    bubble.textContent = text;
    messages.appendChild(bubble);
    messages.scrollTop = messages.scrollHeight;
  }

  if (widget && fab) {
    fab.addEventListener('click', () => widget.classList.toggle('open'));
  }
  if (widget && close) {
    close.addEventListener('click', () => widget.classList.remove('open'));
  }

  if (form) {
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const input = form.querySelector('input[name="message"]');
      const text = input.value.trim();
      if (!text) return;
      addMessage(text, 'user');
      input.value = '';
      const thinking = 'Checking the SecureVote guide...';
      addMessage(thinking, 'bot');
      const lastBot = messages.lastElementChild;
      try {
        const response = await fetch('/assistant/chat', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrf
          },
          body: JSON.stringify({ message: text, csrf_token: csrf })
        });
        const data = await response.json();
        if (lastBot) lastBot.textContent = data.answer || 'I could not answer that question.';
      } catch (error) {
        if (lastBot) lastBot.textContent = 'Assistant connection failed. Check your Flask server and OpenRouter settings.';
      }
    });
  }
});
