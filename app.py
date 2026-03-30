import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from scipy.optimize import linear_sum_assignment
import time

st.set_page_config(page_title="YULfactory: 통합 인력 관제", layout="wide")

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
        'Condition': np.random.uniform(0.8, 1.0, 30),
        'Cum_Exp': [0.0] * 30,
        'Work_Time': [0.0] * 30,
        'is_present': [True] * 30, # 출근 여부 상태
        'Status': ['대기'] * 30 
    })
    st.session_state.colors = {f'W_{i+1:02d}': f'hsl({i*12}, 70%, 50%)' for i in range(30)}
    st.session_state.log = []

# --- [2. 사이드바: 출근 관리 (소프트웨어학과 미션)] ---
st.sidebar.header("🏬 실시간 출근 관리 (30인)")
st.sidebar.caption("체크 해제 시 즉시 현장에서 제외됩니다.")

# 스크롤 가능한 영역처럼 보이기 위해 멀티셀렉트나 반복문 사용
for i in range(30):
    w_id = st.session_state.workers.at[i, 'ID']
    w_lv = st.session_state.workers.at[i, 'Level']
    # 체크박스로 출근 상태 제어
    is_on = st.sidebar.checkbox(f"{w_id} ({w_lv})", value=st.session_state.workers.at[i, 'is_present'], key=f"check_{w_id}")
    
    # 상태가 바뀌면 로직 반영
    if is_on != st.session_state.workers.at[i, 'is_present']:
        st.session_state.workers.at[i, 'is_present'] = is_on
        if not is_on:
            st.session_state.workers.at[i, 'Status'] = '퇴근' # 미출근 시 현장 제외
            st.session_state.log.append(f"🔌 {w_id} 연결 해제 (미출근/조퇴)")
        else:
            st.session_state.workers.at[i, 'Status'] = '대기'
            st.session_state.log.append(f"📡 {w_id} 재연결 (출근 확인)")

# --- [3. 핵심 로직: 동적 교대 및 무한 루프] ---
def manage_rotation():
    workers = st.session_state.workers
    event_msg = None
    
    # A. 근무 중인 사람 중 퇴출 (시간초과, 컨디션불량, 혹은 사이드바에서 체크해제됨)
    on_duty_indices = workers[workers['Status'] == '근무'].index
    for idx in on_duty_indices:
        w = workers.loc[idx]
        if w['Work_Time'] >= 8.0 or w['Condition'] < 0.4 or not w['is_present']:
            reason = "시간종료" if w['Work_Time'] >= 8.0 else "컨디션/수동제외"
            st.session_state.workers.at[idx, 'Status'] = '퇴근'
            event_msg = f"🚨 {w['ID']} 교체 발생 ({reason})"
            st.session_state.log.append(event_msg)

    # B. 가용 대기자 확인 및 사이클 리셋 (IndexError 방지)
    waiting_pool = st.session_state.workers[(st.session_state.workers['Status'] == '대기') & (st.session_state.workers['is_present'])]
    if len(waiting_pool) < 5:
        # 퇴근한 사람 중 'is_present'가 True인 사람만 다시 대기로 (무한 루프)
        st.session_state.workers.loc[(st.session_state.workers['Status'] == '퇴근') & (st.session_state.workers['is_present']), 'Work_Time'] = 0.0
        st.session_state.workers.loc[(st.session_state.workers['Status'] == '퇴근') & (st.session_state.workers['is_present']), 'Status'] = '대기'
        st.session_state.log.append("♻️ 인력 사이클 자동 리셋")

    # C. 현장 10명 유지
    current_duty = st.session_state.workers[st.session_state.workers['Status'] == '근무']
    if len(current_duty) < 10:
        needed = 10 - len(current_duty)
        # 출근 중인 대기자 중 선발
        available_waiting = st.session_state.workers[(st.session_state.workers['Status'] == '대기') & (st.session_state.workers['is_present'])].sort_values('Cum_Exp')
        for idx in available_waiting.iloc[:needed].index:
            st.session_state.workers.at[idx, 'Status'] = '근무'
            st.session_state.log.append(f"🆕 {st.session_state.workers.at[idx, 'ID']} 현장 투입")
            
    return event_msg

# --- [4. 메인 화면] ---
st.title("🛡️ YULfactory: 30인 통합 출근 및 동적 관제")

placeholder = st.empty()

while True:
    msg = manage_rotation()
    
    with placeholder.container():
        on_duty = st.session_state.workers[st.session_state.workers['Status'] == '근무'].head(10)
        actual_count = len(on_duty)
        
        if actual_count < 3:
            st.error("🚨 비상 상황: 가용 인력 부족으로 공정 가동이 불가능합니다!")
            time.sleep(2)
            st.rerun()

        # 환경 및 최적 배정
        voc_matrix = np.random.randint(10, 100, (2, 5))
        booths = [{'X': (i%5)+1, 'Y': 2-(i//5), 'VOC': voc_matrix[i//5, i%5]} for i in range(10)]
        
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
            st.subheader("📋 시스템 로그")
            for l in st.session_state.log[-6:]:
                st.caption(l)
            st.divider()
            st.subheader("📊 현장 근무 현황")
            st.dataframe(on_duty[['ID', 'Level', 'Condition', 'Work_Time']], hide_index=True)

        time.sleep(1.0)
        st.rerun()
