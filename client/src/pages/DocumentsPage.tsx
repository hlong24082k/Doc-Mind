"use client";

import React, { useState, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Upload, FileText, MessageSquare } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useToast } from "@/components/ui/use-toast";

interface Document {
  id: string;
  name: string;
  uploadedDate: string;
}

const DocumentsPage: React.FC = () => {
  const [documents, setDocuments] = useState<Document[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const { toast } = useToast();

  const handleFileUploadClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (files && files.length > 0) {
      const newFile = files[0];
      const newDocument: Document = {
        id: `doc-${Date.now()}`, // Simple unique ID
        name: newFile.name,
        uploadedDate: new Date().toLocaleDateString(),
      };
      setDocuments((prevDocs) => [...prevDocs, newDocument]);
      toast({
        title: "Document Uploaded",
        description: `${newFile.name} has been added to your documents.`,
      });
      // Clear the input so the same file can be uploaded again if needed
      event.target.value = '';
    }
  };

  const handleStartChat = (documentId: string, documentName: string) => {
    navigate(`/chat/${documentId}`, { state: { documentName } });
  };

  return (
    <div className="flex flex-col h-full p-4">
      <h1 className="text-2xl font-bold mb-4">Your Documents</h1>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {documents.map((doc) => (
          <Card key={doc.id}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">
                {doc.name}
              </CardTitle>
              <FileText className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-lg font-bold truncate">{doc.name}</div>
              <p className="text-xs text-muted-foreground">
                Uploaded on {doc.uploadedDate}
              </p>
              <Button
                variant="outline"
                size="sm"
                className="mt-2"
                onClick={() => handleStartChat(doc.id, doc.name)}
              >
                <MessageSquare className="mr-2 h-4 w-4" />
                Start Chat
              </Button>
            </CardContent>
          </Card>
        ))}

        <Card
          className="flex flex-col items-center justify-center p-6 border-2 border-dashed hover:border-primary transition-colors cursor-pointer"
          onClick={handleFileUploadClick}
        >
          <Upload className="h-8 w-8 text-muted-foreground mb-2" />
          <p className="text-sm text-muted-foreground">Upload New Document</p>
          <Button variant="ghost" className="mt-2">Browse Files</Button>
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileChange}
            className="hidden"
            accept=".pdf,.doc,.docx,.txt" // Specify accepted file types
          />
        </Card>
      </div>
    </div>
  );
};

export default DocumentsPage;