async function refresh() {
  try {
    const vars = document.querySelectorAll('.num');
    vars.forEach(v => v.textContent = '…');

    const [runsRes, channelsRes] = await Promise.all([
      fetch('/api/videos?limit=50'),
      fetch('/api/channels'),
    ]);
    if (!runsRes.ok || !channelsRes.ok) throw new Error('API error');

    const videos = await runsRes.json();
    const channels = await channelsRes.json();

    const totalEl = document.getElementById('total');
    const okEl = document.getElementById('successes');
    const failEl = document.getElementById('failures');

    const failed = videos.filter(v => v.status === 'FAILED').length;
    const published = videos.filter(v => v.status === 'PUBLISHED').length;

    totalEl.textContent = videos.length;
    okEl.textContent = published;
    failEl.textContent = failed;

    const tbody = document.getElementById('runs-body');
    tbody.innerHTML = '';
    if (videos.length === 0) {
      const tr = document.createElement('tr');
      const td = document.createElement('td');
      td.colSpan = 5;
      td.className = 'muted';
      td.textContent = 'No runs recorded yet.';
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }

    for (const v of videos) {
      const tr = document.createElement('tr');

      const tdTime = document.createElement('td');
      tdTime.textContent = v.created_at || '';

      const tdChannel = document.createElement('td');
      tdChannel.textContent = v.channel || '';

      const tdTopic = document.createElement('td');
      tdTopic.textContent = v.topic || '';

      const tdStatus = document.createElement('td');
      tdStatus.className = v.status === 'PUBLISHED' ? 'ok' : (v.status === 'FAILED' ? 'fail' : '');
      tdStatus.textContent = v.status || '';

      const tdErr = document.createElement('td');
      tdErr.textContent = v.error_message || '';

      tr.append(tdTime, tdChannel, tdTopic, tdStatus, tdErr);
      tbody.appendChild(tr);
    }
  } catch (err) {
    console.error('Dashboard refresh failed:', err);
  }
}

refresh();
setInterval(refresh, 15000);