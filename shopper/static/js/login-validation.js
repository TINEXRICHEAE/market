// Add this function at the top level
function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === (name + '=')) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

document.addEventListener('DOMContentLoaded', function () {
  const form = document.getElementById('loginForm');
  const emailInput = document.getElementById('email');
  const passwordInput = document.getElementById('password');
  const emailError = document.getElementById('emailError');
  const passwordError = document.getElementById('passwordError');
  const messageBox = document.getElementById('messageBox');

  // Form submission handler
  form.addEventListener('submit', function (event) {
    event.preventDefault();
    let isValid = true;

    // Validate email
    if (!validateEmail(emailInput.value)) {
      emailError.textContent = 'Please enter a valid email address.';
      emailError.style.display = 'block';
      isValid = false;
    } else {
      emailError.style.display = 'none';
    }

    // Validate password
    if (!passwordInput.value) {
      passwordError.textContent = 'Password is required.';
      passwordError.style.display = 'block';
      isValid = false;
    } else {
      passwordError.style.display = 'none';
    }

    // Submit form if valid
    if (isValid) {
      const formData = new FormData(form);
      // Log the form data for debugging
      for (let [key, value] of formData.entries()) {
        console.log(key, value);
      }
      // In the form submission handler, modify the fetch call:
      fetch(form.action, {
        method: 'POST',
        body: formData,
        headers: {
          'X-CSRFToken': getCookie('csrftoken')
        },
      })
        .then((response) => response.json())
        .then((data) => {
          if (data.error) {
            showMessage(data.error, 'error');
          } else {
            showMessage(data.message, 'success');
            setTimeout(() => {
              window.history.back(); // Go back to previous page
            }, 1500);
          }
        })
        .catch((error) => {
          showMessage('An error occurred. Please try again.', 'error');
        });
    }
  });

  // Helper functions
  function validateEmail(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
  }

  function showMessage(message, type) {
    messageBox.textContent = message;
    messageBox.className = `message-box ${type}`;
    messageBox.style.display = 'block';
  }
});