<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8" />
    <title>Video Frame Extractor (FastAPI)</title>
    <style>
      body {
        font-family: sans-serif;
        margin: 20px;
      }
      .frame-container {
        display: flex;
        flex-wrap: wrap;
      }
      .frame-item {
        margin: 10px;
        text-align: center;
      }
      img {
        max-width: 200px;
        display: block;
        margin-bottom: 5px;
      }
      button, input[type=submit] {
        margin: 5px 0;
        padding: 8px 14px;
        font-size: 14px;
      }
      input[type="file"] {
        margin-bottom: 10px;
      }
    </style>
</head>
<body>
<h1>Video Frame Extractor</h1>

{% if message %}
<p><strong>{{ message }}</strong></p>
{% endif %}

<form action="/upload-video" method="post" enctype="multipart/form-data">
  <input type="file" name="file" accept="video/*" required />
  <input type="submit" value="Extract I-Frames" />
</form>

<hr />

<h2>Extracted Frames</h2>
{% if frames %}
<form id="framesForm">
  <div class="frame-container">
  {% for filename in frames %}
    <div class="frame-item">
      <img src="/frames/{{ filename }}" alt="{{ filename }}" />
      <label>
        <input type="checkbox" name="filenames" value="{{ filename }}" />
        {{ filename }}
      </label>
    </div>
  {% endfor %}
  </div>

  <button type="button" onclick="downloadZip()">Download Selected as ZIP</button>
  <button type="button" onclick="downloadIndividual()">Download Individually</button>
</form>
{% else %}
<p>No frames extracted yet.</p>
{% endif %}

<script>
async function downloadZip() {
  const form = document.getElementById('framesForm');
  const formData = new FormData(form);
  let selected = formData.getAll('filenames');
  if (!selected.length) {
    alert("No frames selected.");
    return;
  }

  const body = JSON.stringify({ filenames: selected });
  const resp = await fetch('/download-zip', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body
  });

  if (!resp.ok) {
    const errorData = await resp.json();
    alert(`Error: ${errorData.detail}`);
    return;
  }
  const blob = await resp.blob();
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'frames.zip';
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

async function downloadIndividual() {
  const form = document.getElementById('framesForm');
  const formData = new FormData(form);
  let selected = formData.getAll('filenames');
  if (!selected.length) {
    alert("No frames selected.");
    return;
  }

  const body = JSON.stringify({ filenames: selected });
  const resp = await fetch('/download-individual', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body
  });

  if (!resp.ok) {
    const errorData = await resp.json();
    alert(`Error: ${errorData.detail}`);
    return;
  }
  const blob = await resp.blob();
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'frames.zip';
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}
</script>

</body>
</html>
