import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from scipy.optimize import linear_sum_assignment
import time

st.set_page_config(page_title="YULfactory: 통합 관제 시스템", layout="wide")

# --- [1. 인력 풀 초기화] ---
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
        'Status': ['대기'] * 30 
    })
    st.session_state.colors = {f'W_{i+1:02d}': f'hsl({i*12}, 70%, 50%)' for i in range(30)}
    st.session_state.log = []

# --- [2. 핵심 로직: 교체 발생 체크] ---
def manage_rotation():
    workers = st.session_state.workers
    event_msg = None
    
    # 퇴출: 8초 경과 또는 컨디션 0.4 미만
    to_exit = workers[(workers['Status'] == '근무') & ((workers['Work_Time'] >= 8.0) | (workers['Condition'] < 0.4))]
    
    if not to_exit.empty:
        for idx in to_exit.index:
            reason = "시간 종료" if workers.at[idx, 'Work_Time'] >= 8.0 else "긴급(컨디션)"
            st.session_state.workers.at[idx, 'Status'] = '퇴근'
            event_msg = f"🚨 {workers.at[idx, 'ID']} 교체 ({reason})"
            st.session_state.log.append(event_msg)
        
    # 투입: 10명 유지
    current_count = len(st.session_state.workers[st.session_state.workers['Status'] == '근무'])
    if current_count < 10:
        needed = 10 - current_count
        waiting = st.session_state.workers[st.session_state.workers['Status'] == '대기'].sort_values('Cum_Exp')
        if not waiting.empty:
            for idx in waiting.iloc[:needed].index:
                st.session_state.workers.at[idx, 'Status'] = '근무'
                st.session_state.log.append(f"🆕 {st.session_state.workers.at[idx, 'ID']} 투입")
            event_msg = "🔄 인력 재배치 완료"
            
    return event_msg

# --- [3. 사이드바 제어] ---
st.sidebar.header("🕹️ 관제 설정")
target_worker = st.sidebar.selectbox("컨디션 하락 테스트", st.session_state.workers[st.session_state.workers['Status'] == '근무']['ID'] if not st.session_state.workers[st.session_state.workers['Status'] == '근무'].empty else ["없음"])
if st.sidebar.button("⚠️ 컨디션 강제 하락 (0.2)"):
    st.session_state.workers.loc[st.session_state.workers['ID'] == target_worker, 'Condition'] = 0.2

# --- [4. 메인 화면 구성] ---
st.title("🛡️ 자동차 도장공정: 30인 통합 동적 관제 시스템")

placeholder = st.empty()

while True:
    msg = manage_rotation()
    
    with placeholder.container():
        # 교체 이벤트 발생 시 상단 알림
        if msg:
            st.warning(f"**시스템 메시지:** {msg}")
            time.sleep(1.0)

        # 현재 근무자 10명 선발 및 최적 배정
        on_duty = st.session_state.workers[st.session_state.workers['Status'] == '근무'].iloc[:10]
        voc_matrix = np.random.randint(10, 100, (2, 5))
        booths = [{'X': c+1, 'Y': 2-r, 'VOC': voc_matrix[r, c]} for r in range(2) for c in range(5)]
        
        cost_matrix = np.zeros((10, 10))
        for i in range(10):
            w = on_duty.iloc[i]
            for j in range(10):
                b = booths[j]
                sens = 2.0 if w['Level'] == '신입' else 1.0
                cost_matrix[i, j] = (sens * b['VOC'] + w['Cum_Exp']) / (w['Skill_Weight'] * w['Condition'])
        
        row_ind, col_ind = linear_sum_assignment(cost_matrix)

        # --- 레이아웃 분할 ---
        col_left, col_right = st.columns([2.5, 1])
        
        with col_left:
            st.subheader("🌐 실시간 디지털 트윈 맵")
            fig = go.Figure()
            fig.add_trace(go.Heatmap(z=voc_matrix, x=[1,2,3,4,5], y=[1,2], colorscale='RdYlGn_r', zmin=0, zmax=100, opacity=0.4, showscale=True))
            
            for r, c in zip(row_ind, col_ind):
                w = on_duty.iloc[r]
                b = booths[c]
                # 데이터 실시간 누적
                st.session_state.workers.loc[st.session_state.workers['ID'] == w['ID'], 'Work_Time'] += 0.5
                st.session_state.workers.loc[st.session_state.workers['ID'] == w['ID'], 'Cum_Exp'] += b['VOC'] * 0.02
                
                # 컨디션 불량 시 빨간 테두리
                border = 'red' if w['Condition'] < 0.5 else 'white'
                fig.add_trace(go.Scatter(
                    x=[b['X']], y=[b['Y']], mode="markers+text",
                    marker=dict(size=50, color=st.session_state.colors[w['ID']], line=dict(width=4, color=border)),
                    text=[f"<b>{w['ID']}</b><br>{round(w['Work_Time'],1)}s"], textposition="middle center", showlegend=False
                ))
            fig.update_layout(height=500, margin=dict(l=10, r=10, t=10, b=10), xaxis=dict(title="Booth Column"), yaxis=dict(title="Row"))
            st.plotly_chart(fig, use_container_width=True)

        with col_right:
            st.subheader("📋 실시간 시스템 로그")
            # 로그 창을 깔끔하게 유지하기 위해 최근 6개만 표시
            for l in st.session_state.log[-6:]:
                st.caption(l)
            
            st.divider()
            st.subheader("📊 작업자 상태 데이터")
            # 가독성을 위해 현재 근무자만 정렬해서 표시
            status_df = on_duty[['ID', 'Level', 'Condition', 'Work_Time']].sort_values('Work_Time', ascending=False)
            status_df.columns = ['ID', '숙련도', '컨디션', '시간']
            st.dataframe(status_df, hide_index=True, use_container_width=True)

        time.sleep(1.0)
        st.rerun()
