import React, { useEffect } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { useNavigate, useParams } from 'react-router-dom';

function TestComponent() {
	const dispatch = useDispatch();
	const navigate = useNavigate();
	const { id } = useParams();

	useEffect(() => {
		if (id !== '') {
			dispatch(setId(id));
		}
		return () => {
			dispatch(clearId());
		};
	}, [id, dispatch, navigate]);

	return <div>Test</div>;
}

export default TestComponent;

