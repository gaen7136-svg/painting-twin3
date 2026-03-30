import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from scipy.optimize import linear_sum_assignment
import time

st.set_page_config(page_title="YULfactory: 통합 세이프티 관제", layout="wide")

# --- [1. 데이터 초기화] ---
if 'workers' not in st.session_state:
    ids = [f'W_{i+1:02d}' for i in range(30)]
    levels = ['전문가']*5 + ['숙련공']*15 + ['신입']*10
    np.random.shuffle(levels)
    
    st.session_state.workers = pd.DataFrame({
        'ID': ids,
        'Level': levels,
        'Skill_Weight': [1.2 if l == '전문가' else 1.0 if l == '숙련공' else 0.7 for l in levels],
        'Safety_Margin': [1.0 if l != '신입' else 0.5 for l in levels],
        'Condition': np.random.uniform(0.9, 1.0, 30), # 초기 컨디션은 우수하게
        'Cum_Exp': [0.0] * 30,
        'Work_Time': [0.0] * 30,
        'is_present': [True] * 30,
        'Status': ['대기'] * 30 
    })
    st.session_state.colors = {f'W_{i+1:02d}': f'hsl({i*12}, 70%, 50%)' for i in range(30)}
    st.session_state.log = []

# --- [2. 사이드바: 듀얼 컨트롤 레이아웃] ---
st.sidebar.header("🕹️ 실시간 현장 관제")

# A. 컨디션 긴급 조정 (산업공학/화학 융합 예외 상황)
st.sidebar.subheader("🚑 보건 안전 개입")
current_on_duty_ids = st.session_state.workers[st.session_state.workers['Status'] == '근무']['ID'].tolist()
target_worker = st.sidebar.selectbox("컨디션 하락 타겟", current_on_duty_ids if current_on_duty_ids else ["없음"])

if st.sidebar.button("⚠️ 선택 인원 컨디션 급락 (0.2)"):
    if target_worker != "없음":
        st.session_state.workers.loc[st.session_state.workers['ID'] == target_worker, 'Condition'] = 0.2
        st.toast(f"{target_worker}의 신체 이상 신호 감지! 즉시 교체 대기.")

st.sidebar.divider()

# B. 출근 관리 (소프트웨어/인력 관리 미션)
st.sidebar.subheader("🏬 출근/가용성 관리")
for i in range(30):
    w = st.session_state.workers.iloc[i]
    # 체크박스 상태 변경 시 즉시 반영
    is_checked = st.sidebar.checkbox(f"{w['ID']} ({w['Level']})", value=w['is_present'], key=f"chk_{w['ID']}")
    if is_checked != st.session_state.workers.at[i, 'is_present']:
        st.session_state.workers.at[i, 'is_present'] = is_checked
        if not is_checked:
            st.session_state.workers.at[i, 'Status'] = '퇴근'
            st.session_state.log.append(f"🔌 {w['ID']} 현장 이탈 (결근/조퇴)")
        else:
            st.session_state.workers.at[i, 'Status'] = '대기'
            st.session_state.log.append(f"📡 {w['ID']} 가용 인원 복귀")

# --- [3. 핵심 로직: 자동 교대 및 무한 루프] ---
def manage_rotation():
    workers = st.session_state.workers
    event_msg = None
    
    # 1. 퇴출 로직 (8초 초과 OR 컨디션 0.4 미만 OR 수동 출근해제)
    on_duty_idx = workers[workers['Status'] == '근무'].index
    for idx in on_duty_idx:
        w = workers.loc[idx]
        if w['Work_Time'] >= 8.0 or w['Condition'] < 0.4 or not w['is_present']:
            reason = "시간종료" if w['Work_Time'] >= 8.0 else ("긴급보건" if w['Condition'] < 0.4 else "수동제외")
            st.session_state.workers.at[idx, 'Status'] = '퇴근'
            event_msg = f"🚨 {w['ID']} 현장 교체 ({reason})"
            st.session_state.log.append(event_msg)

    # 2. 무한 루프: 가용 대기자가 부족하면 퇴근자 중 출근 중인 사람 리셋
    waiting_pool = st.session_state.workers[(st.session_state.workers['Status'] == '대기') & (st.session_state.workers['is_present'])]
    if len(waiting_pool) < 5:
        st.session_state.workers.loc[(st.session_state.workers['Status'] == '퇴근') & (st.session_state.workers['is_present']), 'Work_Time'] = 0.0
        st.session_state.workers.loc[(st.session_state.workers['Status'] == '퇴근') & (st.session_state.workers['is_present']), 'Condition'] = 0.95 # 컨디션 회복
        st.session_state.workers.loc[(st.session_state.workers['Status'] == '퇴근') & (st.session_state.workers['is_present']), 'Status'] = '대기'
        st.session_state.log.append("♻️ 인력 사이클 자동 리셋 (24h 모드)")

    # 3. 투입 로직 (10명 유지)
    current_duty = st.session_state.workers[st.session_state.workers['Status'] == '근무']
    if len(current_duty) < 10:
        needed = 10 - len(current_duty)
        available = st.session_state.workers[(st.session_state.workers['Status'] == '대기') & (st.session_state.workers['is_present'])].sort_values('Cum_Exp')
        for idx in available.iloc[:needed].index:
            st.session_state.workers.at[idx, 'Status'] = '근무'
            st.session_state.log.append(f"🆕 {st.session_state.workers.at[idx, 'ID']} 투입")
            
    return event_msg

# --- [4. 메인 시각화 화면] ---
st.title("🛡️ 자동차 도장공정: 30인 동적 관제 센터")
placeholder = st.empty()

while True:
    msg = manage_rotation()
    with placeholder.container():
        if msg:
            st.warning(f"**시스템 이벤트 발생:** {msg}")
            time.sleep(1.0)

        on_duty = st.session_state.workers[st.session_state.workers['Status'] == '근무'].head(10)
        actual_count = len(on_duty)
        
        # 최적 배치 및 맵 생성
        voc_matrix = np.random.randint(10, 100, (2, 5))
        booths = [{'X': (i%5)+1, 'Y': 2-(i//5), 'VOC': voc_matrix[i//5, i%5]} for i in range(10)]
        
        if actual_count > 0:
            cost_matrix = np.zeros((actual_count, actual_count))
            for i in range(actual_count):
                for j in range(actual_count):
                    w = on_duty.iloc[i]
                    b = booths[j]
                    sens = 2.0 if w['Level'] == '신입' else 1.0
                    cost_matrix[i, j] = (sens * b['VOC'] + w['Cum_Exp']) / (w['Skill_Weight'] * w['Condition'])
            row_ind, col_ind = linear_sum_assignment(cost_matrix)

            col_left, col_right = st.columns([2.5, 1])
            with col_left:
                st.subheader("🌐 실시간 디지털 트윈 맵")
                fig = go.Figure()
                fig.add_trace(go.Heatmap(z=voc_matrix, x=[1,2,3,4,5], y=[1,2], colorscale='RdYlGn_r', zmin=0, zmax=100, opacity=0.4))
                
                for i in range(len(row_ind)):
                    w = on_duty.iloc[row_ind[i]]
                    b = booths[col_ind[i]]
                    st.session_state.workers.loc[st.session_state.workers['ID'] == w['ID'], 'Work_Time'] += 0.5
                    st.session_state.workers.loc[st.session_state.workers['ID'] == w['ID'], 'Cum_Exp'] += b['VOC'] * 0.02
                    
                    border = 'red' if w['Condition'] < 0.5 else 'white'
                    fig.add_trace(go.Scatter(
                        x=[b['X']], y=[b['Y']], mode="markers+text",
                        marker=dict(size=45, color=st.session_state.colors[w['ID']], line=dict(width=4, color=border)),
                        text=[f"<b>{w['ID']}</b><br>{round(w['Work_Time'],1)}s"], textposition="middle center", showlegend=False
                    ))
                fig.update_layout(height=480, margin=dict(l=10, r=10, t=10, b=10))
                st.plotly_chart(fig, use_container_width=True)
            
            with col_right:
                st.subheader("📋 실시간 로그")
                for l in st.session_state.log[-6:]:
                    st.caption(l)
                st.divider()
                st.subheader("📊 작업 상태")
                st.dataframe(on_duty[['ID', 'Level', 'Condition', 'Work_Time']].sort_values('Condition'), hide_index=True)
        else:
            st.error("🚨 가용 인력 전원 이탈! 공정 가동을 즉시 중단합니다.")

        time.sleep(1.0)
        st.rerun()
