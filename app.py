import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from scipy.optimize import linear_sum_assignment
import time

st.set_page_config(page_title="YULfactory: 컨디션 기반 강제 교체", layout="wide")

# --- [1. 인력 풀 및 상태 초기화] ---
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

st.title("🛡️ 컨디션 기반 자동 강제 교체 관제 시스템")

# --- [2. 핵심 로직: 교체 발생 체크 (컨디션 로직 포함)] ---
def manage_rotation():
    workers = st.session_state.workers
    replacement_event = False
    
    # 1. 퇴출 대상 선정 (시간 초과 OR 컨디션 불량)
    # 컨디션이 0.4 미만이면 '긴급 교체' 대상으로 분류
    to_exit = workers[(workers['Status'] == '근무') & 
                      ((workers['Work_Time'] >= 8.0) | (workers['Condition'] < 0.4))]
    
    if not to_exit.empty:
        for idx in to_exit.index:
            reason = "시간 초과" if workers.at[idx, 'Work_Time'] >= 8.0 else "컨디션 난조(긴급)"
            st.session_state.workers.at[idx, 'Status'] = '퇴근'
            st.session_state.log.append(f"🚨 {workers.at[idx, 'ID']} 교체됨 ({reason})")
        replacement_event = True
        
    # 2. 신규 투입 (10명 유지)
    current_count = len(st.session_state.workers[st.session_state.workers['Status'] == '근무'])
    if current_count < 10:
        needed = 10 - current_count
        waiting = st.session_state.workers[st.session_state.workers['Status'] == '대기'].sort_values('Cum_Exp')
        if not waiting.empty:
            new_picks = waiting.iloc[:needed]
            for idx in new_picks.index:
                st.session_state.workers.at[idx, 'Status'] = '근무'
                st.session_state.log.append(f"🆕 {st.session_state.workers.at[idx, 'ID']} 대기조에서 투입")
            replacement_event = True
            
    return replacement_event

# --- [3. 사이드바: 시연용 컨디션 공격 버튼] ---
st.sidebar.header("🕹️ 실시간 예외 상황 발생")
target_worker = st.sidebar.selectbox("타겟 작업자", st.session_state.workers[st.session_state.workers['Status'] == '근무']['ID'] if not st.session_state.workers[st.session_state.workers['Status'] == '근무'].empty else ["없음"])
if st.sidebar.button("⚠️ 해당 작업자 컨디션 0.2로 추락"):
    st.session_state.workers.loc[st.session_state.workers['ID'] == target_worker, 'Condition'] = 0.2
    st.toast(f"{target_worker}의 신체 신호 이상 감지!")

# --- [4. 메인 시뮬레이션] ---
placeholder = st.empty()

while True:
    has_event = manage_rotation()
    
    with placeholder.container():
        if has_event:
            st.error("🔄 **[알림] 안전 기준 위반 혹은 교체 주기 도달 - 인력 재배치 실시**")
            time.sleep(1.2)

        on_duty = st.session_state.workers[st.session_state.workers['Status'] == '근무'].iloc[:10]
        
        # 환경 및 최적 배정
        voc_matrix = np.random.randint(10, 100, (2, 5))
        booths = []
        for r in range(2):
            for c in range(5):
                booths.append({'X': c+1, 'Y': 2-r, 'VOC': voc_matrix[r, c]})
        
        cost_matrix = np.zeros((10, 10))
        for i in range(10):
            w = on_duty.iloc[i]
            for j in range(10):
                b = booths[j]
                sens = 2.0 if w['Level'] == '신입' else 1.0
                cost_matrix[i, j] = (sens * b['VOC'] + w['Cum_Exp']) / (w['Skill_Weight'] * w['Condition'])
        
        row_ind, col_ind = linear_sum_assignment(cost_matrix)

        # 시각화 화면
        col_left, col_right = st.columns([2, 1])
        
        with col_left:
            st.subheader("🌐 디지털 트윈 관제 맵")
            fig = go.Figure()
            fig.add_trace(go.Heatmap(z=voc_matrix, x=[1,2,3,4,5], y=[1,2], colorscale='RdYlGn_r', zmin=0, zmax=100, opacity=0.4))
            
            for r, c in zip(row_ind, col_ind):
                w = on_duty.iloc[r]
                b = booths[c]
                st.session_state.workers.loc[st.session_state.workers['ID'] == w['ID'], 'Work_Time'] += 0.5
                st.session_state.workers.loc[st.session_state.workers['ID'] == w['ID'], 'Cum_Exp'] += b['VOC'] * 0.02
                
                # 시인성을 위해 컨디션이 나쁘면 테두리를 빨갛게
                border_color = 'red' if w['Condition'] < 0.5 else 'white'
                fig.add_trace(go.Scatter(
                    x=[b['X']], y=[b['Y']], mode="markers+text",
                    marker=dict(size=45, color=st.session_state.colors[w['ID']], line=dict(width=4, color=border_color)),
                    text=[f"<b>{w['ID']}</b><br>{round(w['Condition'],1)}"], textposition="middle center", showlegend=False
                ))
            fig.update_layout(height=450, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)

        with col_right:
            st.subheader("📋 실시간 교체/사고 로그")
            for log_msg in st.session_state.log[-8:]:
                if "긴급" in log_msg:
                    st.write(f"🆘 :red[{log_msg}]")
                else:
                    st.write(log_msg)
            
            st.divider()
            st.subheader("📊 근무자 컨디션")
            st.dataframe(on_duty[['ID', 'Level', 'Condition', 'Work_Time']].sort_values('Condition'), hide_index=True)

        time.sleep(1.0)
        st.rerun()
