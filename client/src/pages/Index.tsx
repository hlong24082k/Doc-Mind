"use client";

import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

const Index = () => {
  const navigate = useNavigate();

  useEffect(() => {
    // navigate("/login");
  }, [navigate]);

  return (
    <div className="h-full flex items-center justify-center bg-gray-100">
      <div className="text-center">
        <h1 className="text-4xl font-bold mb-4">Loading...</h1>
        <p className="text-xl text-gray-600">
          Redirecting to login page.
        </p>
      </div>
    </div>
  );
};

export default Index;4