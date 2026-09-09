// 换能器设备实验预约系统 · 手机端优先前端交互逻辑 (含人员下拉、添加人员及域名优先)

let currentWeekStartDate = null; // 当前周一 Date 对象
let selectedDateStr = null;      // 当前选中的某一天 (YYYY-MM-DD)
let isViewAllDays = false;       // 是否查看整周全貌
let currentReservations = [];    // 当前周所有预约数据
let membersList = [];            // 实验人员列表
let systemInfo = null;           // 局域网/系统信息

const WEEKDAY_NAMES = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];

// 日期辅助函数
function formatDate(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function formatShortDate(d) {
  return `${String(d.getMonth() + 1).padStart(2, '0')}/${String(d.getDate()).padStart(2, '0')}`;
}

function getMonday(d) {
  const date = new Date(d);
  const day = date.getDay();
  const diff = date.getDate() - day + (day === 0 ? -6 : 1);
  date.setDate(diff);
  date.setHours(0, 0, 0, 0);
  return date;
}

// 页面加载启动
document.addEventListener('DOMContentLoaded', () => {
  currentWeekStartDate = getMonday(new Date());
  selectedDateStr = formatDate(new Date()); // 默认选中今天

  // 点击遮罩自动关闭底部抽屉
  document.querySelectorAll('.sheet-overlay').forEach(overlay => {
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) {
        overlay.classList.remove('active');
      }
    });
  });

  loadSystemInfo();
  loadMembers();
  loadWeekData();
});

// 获取局域网及系统信息
async function loadSystemInfo() {
  try {
    const res = await fetch('/api/system-info');
    if (res.ok) {
      systemInfo = await res.json();
    }
  } catch (err) {
    console.error('获取局域网信息失败:', err);
  }
}

// ----------------- 实验人员库加载与添加 -----------------
async function loadMembers(selectedName = null) {
  try {
    const res = await fetch('/api/members');
    if (res.ok) {
      membersList = await res.json();
      renderMemberDropdowns(selectedName);
    }
  } catch (err) {
    console.error('加载人员列表失败:', err);
  }
}

function renderMemberDropdowns(selectedName = null) {
  const createSelect = document.getElementById('createUserName');
  const editSelect = document.getElementById('editUserName');

  const currentCreateVal = selectedName || createSelect.value;
  const currentEditVal = editSelect.value;

  let optionsHtml = '<option value="">-- 请选择实验人员 --</option>';
  membersList.forEach(m => {
    optionsHtml += `<option value="${escapeHtml(m.name)}">${escapeHtml(m.name)}</option>`;
  });

  createSelect.innerHTML = optionsHtml;
  editSelect.innerHTML = optionsHtml;

  if (currentCreateVal) createSelect.value = currentCreateVal;
  if (currentEditVal) editSelect.value = currentEditVal;
}

// 提示添加新成员
async function promptAddMember(targetForm) {
  const name = prompt('请输入新实验人员姓名（例如：王五）：');
  if (!name || !name.trim()) return;

  const trimmed = name.trim();
  try {
    const res = await fetch('/api/members', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: trimmed })
    });
    const result = await res.json();
    if (!res.ok) {
      showToast(result.detail || '添加失败', 'error');
      return;
    }
    showToast(`✅ 已将「${trimmed}」加入实验室成员名单！`, 'success');
    await loadMembers(trimmed);
    // 自动在对应的下拉框选中它
    if (targetForm === 'create') {
      document.getElementById('createUserName').value = trimmed;
    } else if (targetForm === 'edit') {
      document.getElementById('editUserName').value = trimmed;
    }
  } catch (err) {
    showToast('网络错误，添加人员失败', 'error');
  }
}

// ----------------- 周切换与模式定位 -----------------
function changeWeek(offset) {
  const newDate = new Date(currentWeekStartDate);
  newDate.setDate(newDate.getDate() + offset * 7);
  currentWeekStartDate = newDate;
  selectedDateStr = formatDate(currentWeekStartDate);
  loadWeekData();
}

function goToCurrentWeek() {
  currentWeekStartDate = getMonday(new Date());
  selectedDateStr = formatDate(new Date());
  loadWeekData();
  showToast('已定位至【本周安排】');
}

function goToNextWeek() {
  const monday = getMonday(new Date());
  monday.setDate(monday.getDate() + 7);
  currentWeekStartDate = monday;
  selectedDateStr = formatDate(monday);
  loadWeekData();
  showToast('已切换至【👉 下一周排期】，请提前锁定时间！', 'success');
}

// 加载一周的数据
async function loadWeekData() {
  const weekStart = new Date(currentWeekStartDate);
  const weekEnd = new Date(currentWeekStartDate);
  weekEnd.setDate(weekEnd.getDate() + 6);

  const startStr = formatDate(weekStart);
  const endStr = formatDate(weekEnd);

  // 联动更新顶部切换 Tab
  const thisWeekStart = formatDate(getMonday(new Date()));
  const nextWeekMon = getMonday(new Date());
  nextWeekMon.setDate(nextWeekMon.getDate() + 7);
  const nextWeekStart = formatDate(nextWeekMon);

  const tabCurr = document.getElementById('tabCurrentWeek');
  const tabNext = document.getElementById('tabNextWeek');
  if (startStr === thisWeekStart) {
    tabCurr.classList.add('active');
    tabNext.classList.remove('active');
  } else if (startStr === nextWeekStart) {
    tabCurr.classList.remove('active');
    tabNext.classList.add('active');
  } else {
    tabCurr.classList.remove('active');
    tabNext.classList.remove('active');
  }

  // 周期标签文字
  const labelEl = document.getElementById('weekRangeLabel');
  labelEl.innerText = `周期：${startStr} 至 ${endStr}`;

  try {
    const res = await fetch(`/api/reservations?start_date=${startStr}&end_date=${endStr}`);
    if (!res.ok) throw new Error('网络请求异常');
    currentReservations = await res.json();
    renderDayPills();
    renderScheduleStream();
  } catch (err) {
    showToast('获取预约数据失败，请刷新', 'error');
  }
}

// ----------------- 渲染横向滑动星期胶囊 -----------------
function renderDayPills() {
  const container = document.getElementById('dayPillsContainer');
  container.innerHTML = '';

  const todayStr = formatDate(new Date());

  for (let i = 0; i < 7; i++) {
    const d = new Date(currentWeekStartDate);
    d.setDate(d.getDate() + i);
    const dateStr = formatDate(d);
    const isToday = dateStr === todayStr;
    const isSelected = dateStr === selectedDateStr && !isViewAllDays;

    const count = currentReservations.filter(r => r.reserve_date === dateStr).length;

    const pill = document.createElement('div');
    pill.className = `day-pill ${isSelected ? 'active' : ''} ${isToday ? 'is-today' : ''}`;
    pill.onclick = () => selectDay(dateStr);

    let statusHtml = '';
    if (count > 0) {
      statusHtml = `<span class="day-status-dot has-res">${count}人约</span>`;
    } else {
      statusHtml = `<span class="day-status-dot all-free">空闲</span>`;
    }

    pill.innerHTML = `
      <div class="day-name">${WEEKDAY_NAMES[i]}${isToday ? '·今' : ''}</div>
      <div class="day-date">${formatShortDate(d)}</div>
      ${statusHtml}
    `;

    container.appendChild(pill);
  }
}

function selectDay(dateStr) {
  selectedDateStr = dateStr;
  isViewAllDays = false;
  updateViewAllButtonText();
  renderDayPills();
  renderScheduleStream();
}

function toggleViewAllDays() {
  isViewAllDays = !isViewAllDays;
  updateViewAllButtonText();
  renderDayPills();
  renderScheduleStream();
}

function updateViewAllButtonText() {
  const icon = document.getElementById('viewAllIcon');
  const text = document.getElementById('viewAllText');
  if (isViewAllDays) {
    icon.innerText = '📅';
    text.innerText = '收起为单日视图';
  } else {
    icon.innerText = '📑';
    text.innerText = '查看整周全貌';
  }
}

// ----------------- 渲染排班内容流与智能空闲建议 -----------------
function renderScheduleStream() {
  const container = document.getElementById('scheduleStream');
  container.innerHTML = '';

  if (isViewAllDays) {
    for (let i = 0; i < 7; i++) {
      const d = new Date(currentWeekStartDate);
      d.setDate(d.getDate() + i);
      const dateStr = formatDate(d);
      renderDaySection(container, dateStr, d, WEEKDAY_NAMES[i]);
    }
  } else {
    const d = new Date(selectedDateStr + 'T00:00:00');
    const dayIndex = (d.getDay() + 6) % 7;
    renderDaySection(container, selectedDateStr, d, WEEKDAY_NAMES[dayIndex], true);
  }
}

function renderDaySection(container, dateStr, dateObj, weekdayName, isSingleDay = false) {
  const dayReservations = currentReservations
    .filter(r => r.reserve_date === dateStr)
    .sort((a, b) => a.start_time.localeCompare(b.start_time));

  const section = document.createElement('div');
  section.style.marginBottom = '16px';

  const todayStr = formatDate(new Date());
  const isToday = dateStr === todayStr;

  const header = document.createElement('div');
  header.className = 'date-section-header';
  header.innerHTML = `
    <div>
      <span>${weekdayName} (${formatShortDate(dateObj)})</span>
      ${isToday ? '<span style="color:#2563eb; font-weight:bold; margin-left:4px;">[今天]</span>' : ''}
    </div>
    <div class="sub-badge">
      ${dayReservations.length > 0 ? `已安排 ${dayReservations.length} 场实验` : '全天空闲'}
    </div>
  `;
  section.appendChild(header);

  // 全天空闲
  if (dayReservations.length === 0) {
    const emptyCard = document.createElement('div');
    emptyCard.className = 'all-free-card';
    emptyCard.innerHTML = `
      <div class="all-free-icon">🎉</div>
      <div class="all-free-title">该日换能器全天空闲</div>
      <div class="all-free-desc">暂无其他同学预约，可优先抢占黄金实验时段</div>
      <button class="btn-card-action primary" style="padding:10px 20px; font-size:0.9rem;" onclick="openCreateSheet('${dateStr}', '09:00', '12:00')">
        ➕ 预约该日实验
      </button>
    `;
    section.appendChild(emptyCard);
    container.appendChild(section);
    return;
  }

  // 计算空闲缝隙（按 08:30 ~ 22:00 计算）
  const WORK_START = "08:30";
  const WORK_END = "22:00";
  let cursor = WORK_START;

  dayReservations.forEach(r => {
    if (r.start_time > cursor) {
      const freeSlot = createFreeSlotElement(dateStr, cursor, r.start_time);
      if (freeSlot) section.appendChild(freeSlot);
    }

    // 渲染预约卡片 (已去除联系方式/工位)
    const resCard = document.createElement('div');
    resCard.className = 'res-card';
    resCard.innerHTML = `
      <div class="res-card-top">
        <div class="res-time-badge">⏰ ${r.start_time} ~ ${r.end_time}</div>
        ${r.has_pin ? '<span style="font-size:0.75rem; color:#f59e0b;">🔒带密码</span>' : ''}
      </div>
      <div class="res-user-name">
        <span>👤 ${escapeHtml(r.user_name)}</span>
      </div>
      ${r.purpose ? `<div class="res-purpose-text">🔬 ${escapeHtml(r.purpose)}</div>` : ''}
      <div class="res-actions-row">
        <button class="btn-card-action" onclick="openEditSheetById(${r.id})">⚙️ 修改时间 / 转让人</button>
      </div>
    `;
    section.appendChild(resCard);

    if (r.end_time > cursor) {
      cursor = r.end_time;
    }
  });

  if (cursor < WORK_END) {
    const trailingFree = createFreeSlotElement(dateStr, cursor, WORK_END);
    if (trailingFree) section.appendChild(trailingFree);
  }

  container.appendChild(section);
}

function createFreeSlotElement(dateStr, start, end) {
  const [sH, sM] = start.split(':').map(Number);
  const [eH, eM] = end.split(':').map(Number);
  const duration = (eH * 60 + eM) - (sH * 60 + sM);
  if (duration < 20) return null;

  const card = document.createElement('div');
  card.className = 'free-slot-card';
  card.style.margin = '6px 0';
  card.onclick = () => openCreateSheet(dateStr, start, end);
  card.innerHTML = `
    <div class="free-slot-info">
      <span>✨ ${start} ~ ${end}</span>
      <span class="free-slot-tag">空闲可约</span>
    </div>
    <div class="free-slot-btn">
      <span>点击预约</span>
      <span>›</span>
    </div>
  `;
  return card;
}

// ----------------- 抽屉控制 -----------------
function openSheet(id) {
  document.getElementById(id).classList.add('active');
}

function closeSheet(id) {
  document.getElementById(id).classList.remove('active');
}

// 打开新建抽屉
function openCreateSheet(defaultDate = null, startTime = '09:00', endTime = '12:00') {
  document.getElementById('createAlert').style.display = 'none';
  document.getElementById('createPurpose').value = '';
  document.getElementById('createPin').value = '';

  document.getElementById('createDate').value = defaultDate || selectedDateStr || formatDate(currentWeekStartDate);
  document.getElementById('createStartTime').value = startTime;
  document.getElementById('createEndTime').value = endTime;

  // 保证人员下拉列表已渲染
  renderMemberDropdowns();

  openSheet('createSheet');
}

function fillTimeSlot(prefix, start, end) {
  document.getElementById(`${prefix}StartTime`).value = start;
  document.getElementById(`${prefix}EndTime`).value = end;
}

// 提交新建预约
async function handleCreateSubmit(e) {
  e.preventDefault();
  const alertBox = document.getElementById('createAlert');
  alertBox.style.display = 'none';

  const userName = document.getElementById('createUserName').value.trim();
  if (!userName) {
    alertBox.innerText = '请选择实验人员！';
    alertBox.style.display = 'block';
    return;
  }

  const payload = {
    user_name: userName,
    contact: '',
    reserve_date: document.getElementById('createDate').value,
    start_time: document.getElementById('createStartTime').value,
    end_time: document.getElementById('createEndTime').value,
    purpose: document.getElementById('createPurpose').value.trim(),
    pin: document.getElementById('createPin').value.trim()
  };

  if (payload.start_time >= payload.end_time) {
    alertBox.innerText = '开始时间必须早于结束时间！';
    alertBox.style.display = 'block';
    return;
  }

  const btn = document.getElementById('btnSubmitCreate');
  btn.disabled = true;
  btn.innerText = '正在校验排期...';

  try {
    const res = await fetch('/api/reservations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const result = await res.json();

    if (!res.ok) {
      alertBox.innerText = result.detail || '预约失败，请检查时间';
      alertBox.style.display = 'block';
      return;
    }

    showToast('🎉 换能器设备预约成功！', 'success');
    closeSheet('createSheet');
    selectedDateStr = payload.reserve_date;
    currentWeekStartDate = getMonday(new Date(payload.reserve_date + 'T00:00:00'));
    loadWeekData();
  } catch (err) {
    alertBox.innerText = '网络异常，请确认网络连接';
    alertBox.style.display = 'block';
  } finally {
    btn.disabled = false;
    btn.innerText = '确认预约 (防撞车校验)';
  }
}

// 打开修改抽屉
function openEditSheetById(id) {
  const item = currentReservations.find(r => r.id === id);
  if (!item) return;

  document.getElementById('editAlert').style.display = 'none';
  document.getElementById('editId').value = item.id;
  
  // 设置人员下拉框值
  renderMemberDropdowns();
  document.getElementById('editUserName').value = item.user_name;

  document.getElementById('editDate').value = item.reserve_date;
  document.getElementById('editStartTime').value = item.start_time;
  document.getElementById('editEndTime').value = item.end_time;
  document.getElementById('editPurpose').value = item.purpose || '';
  document.getElementById('editPin').value = '';

  const pinGroup = document.getElementById('editPinGroup');
  if (item.has_pin) {
    pinGroup.querySelector('label').innerHTML = 'PIN码验证 <span style="color:#ef4444;">* (该时段已设PIN码)</span>';
  } else {
    pinGroup.querySelector('label').innerHTML = 'PIN码验证 (未设置PIN码，可留空直接修改)';
  }

  openSheet('editSheet');
}

// 提交修改
async function handleEditSubmit(e) {
  e.preventDefault();
  const alertBox = document.getElementById('editAlert');
  alertBox.style.display = 'none';

  const userName = document.getElementById('editUserName').value.trim();
  if (!userName) {
    alertBox.innerText = '请选择实验人员！';
    alertBox.style.display = 'block';
    return;
  }

  const id = document.getElementById('editId').value;
  const payload = {
    user_name: userName,
    contact: '',
    reserve_date: document.getElementById('editDate').value,
    start_time: document.getElementById('editStartTime').value,
    end_time: document.getElementById('editEndTime').value,
    purpose: document.getElementById('editPurpose').value.trim(),
    pin: document.getElementById('editPin').value.trim()
  };

  if (payload.start_time >= payload.end_time) {
    alertBox.innerText = '开始时间必须早于结束时间！';
    alertBox.style.display = 'block';
    return;
  }

  const btn = document.getElementById('btnSubmitEdit');
  btn.disabled = true;
  btn.innerText = '保存中...';

  try {
    const res = await fetch(`/api/reservations/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const result = await res.json();

    if (!res.ok) {
      alertBox.innerText = result.detail || '修改失败';
      alertBox.style.display = 'block';
      return;
    }

    showToast('✅ 预约调整成功！已同步人员与时段', 'success');
    closeSheet('editSheet');
    loadWeekData();
  } catch (err) {
    alertBox.innerText = '网络连接错误，请稍后重试';
    alertBox.style.display = 'block';
  } finally {
    btn.disabled = false;
    btn.innerText = '保存修改';
  }
}

// 取消预约
async function handleDeleteCurrent() {
  const id = document.getElementById('editId').value;
  const pin = document.getElementById('editPin').value.trim();

  if (!confirm('确定要取消此实验预约吗？时段将立即释放供其他同学使用。')) {
    return;
  }

  try {
    const res = await fetch(`/api/reservations/${id}?pin=${encodeURIComponent(pin)}`, {
      method: 'DELETE'
    });
    const result = await res.json();

    if (!res.ok) {
      const alertBox = document.getElementById('editAlert');
      alertBox.innerText = result.detail || '取消失败';
      alertBox.style.display = 'block';
      return;
    }

    showToast('🗑️ 预约已取消，设备时段已释放！');
    closeSheet('editSheet');
    loadWeekData();
  } catch (err) {
    showToast('网络错误，取消失败', 'error');
  }
}

// ----------------- 手机扫码与域名优先策略 -----------------
function getBestDomainUrl() {
  // 1. 优先读取用户在本地配置并保存过的自定义域名
  const savedDomain = localStorage.getItem('transducer_custom_domain');
  if (savedDomain && savedDomain.trim()) {
    return savedDomain.trim();
  }

  // 2. 如果当前页面已经是通过域名访问的（hostname 不是 localhost 且不是纯 IP）
  const host = window.location.hostname;
  const isIpOrLocal = host === 'localhost' || host === '127.0.0.1' || /^(\d{1,3}\.){3}\d{1,3}$/.test(host);
  if (!isIpOrLocal) {
    return window.location.origin;
  }

  // 3. 默认提供一个推荐域名格式或当前地址
  return window.location.origin;
}

function openQrModal() {
  const currentBestUrl = getBestDomainUrl();
  const inputEl = document.getElementById('customDomainInput');
  inputEl.value = currentBestUrl;

  renderDomainQr(currentBestUrl);
  openSheet('qrSheet');
}

function updateDomainQrCode() {
  let val = document.getElementById('customDomainInput').value.trim();
  if (!val) {
    showToast('请输入有效的域名访问地址！', 'error');
    return;
  }
  if (!val.startsWith('http://') && !val.startsWith('https://')) {
    val = 'http://' + val;
    document.getElementById('customDomainInput').value = val;
  }

  localStorage.setItem('transducer_custom_domain', val);
  renderDomainQr(val);
  showToast('✅ 二维码已更新为指定域名！', 'success');
}

function renderDomainQr(targetUrl) {
  document.getElementById('qrUrlDisplay').innerText = targetUrl;
  const qrContainer = document.getElementById('qrcodeCanvas');
  qrContainer.innerHTML = '';
  try {
    if (window.QRCode) {
      new QRCode(qrContainer, {
        text: targetUrl,
        width: 200,
        height: 200,
        colorDark: '#0f172a',
        colorLight: '#ffffff'
      });
    }
  } catch (e) {
    console.error('QRCode 渲染异常:', e);
  }
}

function copyCurrentUrl() {
  const url = document.getElementById('qrUrlDisplay').innerText;
  copyToClipboard(url, '📱 手机访问域名已复制！可在手机浏览器直接打开');
}

// ----------------- 微信群排班与 Excel -----------------
async function openTextSummaryModal() {
  const weekStart = new Date(currentWeekStartDate);
  const weekEnd = new Date(currentWeekStartDate);
  weekEnd.setDate(weekEnd.getDate() + 6);

  const startStr = formatDate(weekStart);
  const endStr = formatDate(weekEnd);

  try {
    const res = await fetch(`/api/export/text?start_date=${startStr}&end_date=${endStr}`);
    if (!res.ok) throw new Error('生成失败');
    const data = await res.json();
    document.getElementById('textSummaryContent').value = data.text;
    openSheet('textSummarySheet');
  } catch (err) {
    showToast('生成群排班文本失败', 'error');
  }
}

function copySummaryText() {
  const textarea = document.getElementById('textSummaryContent');
  copyToClipboard(textarea.value, '📋 排班文本已复制！直接去微信群粘贴发送即可');
  closeSheet('textSummarySheet');
}

function downloadExcel() {
  const weekStart = new Date(currentWeekStartDate);
  const weekEnd = new Date(currentWeekStartDate);
  weekEnd.setDate(weekEnd.getDate() + 6);
  const startStr = formatDate(weekStart);
  const endStr = formatDate(weekEnd);

  window.open(`/api/export/excel?start_date=${startStr}&end_date=${endStr}`, '_blank');
  showToast('正在导出 Excel 排班表...');
}

// 辅助工具
function copyToClipboard(text, successMsg = '已复制到剪贴板') {
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(() => {
      showToast(successMsg, 'success');
    }).catch(() => fallbackCopy(text, successMsg));
  } else {
    fallbackCopy(text, successMsg);
  }
}

function fallbackCopy(text, successMsg) {
  const input = document.createElement('textarea');
  input.value = text;
  document.body.appendChild(input);
  input.select();
  try {
    document.execCommand('copy');
    showToast(successMsg, 'success');
  } catch (e) {
    showToast('复制失败，请手动选择复制', 'error');
  }
  document.body.removeChild(input);
}

function showToast(msg, type = 'normal') {
  const container = document.getElementById('toastContainer');
  const toast = document.createElement('div');
  toast.className = `toast ${type === 'success' ? 'toast-success' : (type === 'error' ? 'toast-error' : '')}`;
  toast.innerText = msg;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translate(-50%, -15px)';
    toast.style.transition = 'all 0.25s ease';
    setTimeout(() => toast.remove(), 250);
  }, 2400);
}

function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
}
